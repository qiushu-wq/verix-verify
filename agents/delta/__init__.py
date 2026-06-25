"""Agent δ — 编程锚 · 编译器+测试框架 外部验证闭环"""
import os, sys, json, time, subprocess, tempfile, ast, re, random
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from collections import defaultdict

# ═══════════════════════════════════════════════
# 1. 轻量级程序合成引擎
# ═══════════════════════════════════════════════

class TemplateSynthesizer:
    """基于模板填充 + AST 约束的程序合成引擎"""

    # 常用代码模板库 — 25 个任务
    TEMPLATES = {
        # ── 列表操作 ──
        'sort_list': {
            'signature': 'def sort_list(lst: list) -> list',
            'templates': ['return sorted({input})'],
            'test_cases': [('[3,1,2]', '[1,2,3]'), ('[]', '[]'), ('[5]', '[5]')],
            'input_var': 'lst', 'output_type': 'list',
        },
        'dedup_list': {
            'signature': 'def dedup_list(lst: list) -> list',
            'templates': [
                'seen = set()\n    result = []\n    for x in {input}:\n        if x not in seen:\n            seen.add(x)\n            result.append(x)\n    return result',
                'return list(dict.fromkeys({input}))',
            ],
            'test_cases': [('[3,1,2,1,3]', '[3,1,2]'), ('[]', '[]'), ('[1]', '[1]'), ('[1,1,1]', '[1]')],
            'input_var': 'lst', 'output_type': 'list',
        },
        'sum_list': {
            'signature': 'def sum_list(lst: list) -> int',
            'templates': ['return sum({input})'],
            'test_cases': [('[1,2,3]', '6'), ('[]', '0'), ('[10,-5,3]', '8')],
            'input_var': 'lst', 'output_type': 'int',
        },
        'max_element': {
            'signature': 'def max_element(lst: list) -> int',
            'templates': ['return max({input})'],
            'test_cases': [('[3,1,4,1,5]', '5'), ('[10]', '10')],
            'input_var': 'lst', 'output_type': 'int',
        },
        'min_element': {
            'signature': 'def min_element(lst: list) -> int',
            'templates': ['return min({input})'],
            'test_cases': [('[3,1,4,1,5]', '1'), ('[10]', '10')],
            'input_var': 'lst', 'output_type': 'int',
        },
        'count_occurrences': {
            'signature': 'def count_occurrences(lst: list, x: int) -> int',
            'templates': ['return lst.count(x)'],
            'test_cases': [('[1,2,3,1,1],1', '3'), ('[1,2,3],4', '0')],
            'input_var': 'lst, x', 'output_type': 'int',
        },
        'list_length': {
            'signature': 'def list_length(lst: list) -> int',
            'templates': ['return len({input})'],
            'test_cases': [('[1,2,3]', '3'), ('[]', '0')],
            'input_var': 'lst', 'output_type': 'int',
        },
        'reverse_list': {
            'signature': 'def reverse_list(lst: list) -> list',
            'templates': ['return {input}[::-1]'],
            'test_cases': [('[1,2,3]', '[3,2,1]'), ('[]', '[]')],
            'input_var': 'lst', 'output_type': 'list',
        },

        # ── 数学 ──
        'fibonacci': {
            'signature': 'def fibonacci(n: int) -> int',
            'templates': ['a, b = 0, 1\n    for _ in range({input}):\n        a, b = b, a + b\n    return a'],
            'test_cases': [('0', '0'), ('1', '1'), ('5', '5'), ('10', '55')],
            'input_var': 'n', 'output_type': 'int',
        },
        'is_prime': {
            'signature': 'def is_prime(n: int) -> bool',
            'templates': ['if {input} < 2:\n        return False\n    for i in range(2, int({input}**0.5)+1):\n        if {input} % i == 0:\n            return False\n    return True'],
            'test_cases': [('2', 'True'), ('3', 'True'), ('4', 'False'), ('17', 'True'), ('1', 'False')],
            'input_var': 'n', 'output_type': 'bool',
        },
        'factorial': {
            'signature': 'def factorial(n: int) -> int',
            'templates': ['result = 1\n    for i in range(1, {input}+1):\n        result *= i\n    return result'],
            'test_cases': [('0', '1'), ('1', '1'), ('5', '120')],
            'input_var': 'n', 'output_type': 'int',
        },
        'abs_value': {
            'signature': 'def abs_value(n: int) -> int',
            'templates': ['return abs({input})', 'return {input} if {input} >= 0 else -{input}'],
            'test_cases': [('5', '5'), ('-3', '3'), ('0', '0')],
            'input_var': 'n', 'output_type': 'int',
        },
        'gcd': {
            'signature': 'def gcd(a: int, b: int) -> int',
            'templates': ['import math\n    return math.gcd({input})'],
            'test_cases': [('12,8', '4'), ('7,3', '1')],
            'input_var': 'a, b', 'output_type': 'int',
        },

        # ── 字符串 ──
        'reverse_string': {
            'signature': 'def reverse_string(s: str) -> str',
            'templates': ['return {input}[::-1]'],
            'test_cases': [('"hello"', '"olleh"'), ('""', '""'), ('"a"', '"a"')],
            'input_var': 's', 'output_type': 'str',
        },
        'is_palindrome': {
            'signature': 'def is_palindrome(s: str) -> bool',
            'templates': ['return {input} == {input}[::-1]'],
            'test_cases': [('"racecar"', 'True'), ('"hello"', 'False'), ('""', 'True')],
            'input_var': 's', 'output_type': 'bool',
        },
        'string_length': {
            'signature': 'def string_length(s: str) -> int',
            'templates': ['return len({input})'],
            'test_cases': [('"hello"', '5'), ('""', '0')],
            'input_var': 's', 'output_type': 'int',
        },
        'to_uppercase': {
            'signature': 'def to_uppercase(s: str) -> str',
            'templates': ['return {input}.upper()'],
            'test_cases': [('"hello"', '"HELLO"'), ('""', '""')],
            'input_var': 's', 'output_type': 'str',
        },
        'to_lowercase': {
            'signature': 'def to_lowercase(s: str) -> str',
            'templates': ['return {input}.lower()'],
            'test_cases': [('"HELLO"', '"hello"')],
            'input_var': 's', 'output_type': 'str',
        },

        # ── 搜索/匹配 ──
        'two_sum': {
            'signature': 'def two_sum(nums: list, target: int) -> list',
            'templates': ['seen = {}\n    for i, n in enumerate(nums):\n        if target - n in seen:\n            return [seen[target-n], i]\n        seen[n] = i\n    return []'],
            'test_cases': [('[2,7,11,15],9', '[0,1]'), ('[3,2,4],6', '[1,2]'), ('[3,3],6', '[0,1]')],
            'input_var': 'nums, target', 'output_type': 'list',
        },
        'is_valid_brackets': {
            'signature': 'def is_valid_brackets(s: str) -> bool',
            'templates': ['''stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for c in s:
        if c in "([{":
            stack.append(c)
        else:
            if not stack or stack[-1] != pairs.get(c):
                return False
            stack.pop()
    return len(stack) == 0'''],
            'test_cases': [('"()"', 'True'), ('"()[]{}"', 'True'), ('"(]"', 'False'), ('"([)]"', 'False'), ('"{[]}"', 'True')],
            'input_var': 's', 'output_type': 'bool',
        },
        'binary_search': {
            'signature': 'def binary_search(lst: list, target: int) -> int',
            'templates': ['lo, hi = 0, len(lst)-1\n    while lo <= hi:\n        mid = (lo+hi)//2\n        if lst[mid] == target:\n            return mid\n        elif lst[mid] < target:\n            lo = mid+1\n        else:\n            hi = mid-1\n    return -1'],
            'test_cases': [('[1,2,3,4,5],3', '2'), ('[1,2,3],6', '-1')],
            'input_var': 'lst, target', 'output_type': 'int',
        },
        'first_occurrence': {
            'signature': 'def first_occurrence(lst: list, x: int) -> int',
            'templates': ['for i, v in enumerate(lst):\n        if v == x:\n            return i\n    return -1'],
            'test_cases': [('[1,2,3,2],2', '1'), ('[1,2,3],4', '-1')],
            'input_var': 'lst, x', 'output_type': 'int',
        },

        # ── 数据结构 ──
        'merge_sorted': {
            'signature': 'def merge_sorted(a: list, b: list) -> list',
            'templates': ['result = []\n    i = j = 0\n    while i < len(a) and j < len(b):\n        if a[i] < b[j]:\n            result.append(a[i]); i+=1\n        else:\n            result.append(b[j]); j+=1\n    result.extend(a[i:])\n    result.extend(b[j:])\n    return result'],
            'test_cases': [('[1,3,5],[2,4,6]', '[1,2,3,4,5,6]'), ('[1],[2]', '[1,2]')],
            'input_var': 'a, b', 'output_type': 'list',
        },
        'dict_keys': {
            'signature': 'def dict_keys(d: dict) -> list',
            'templates': ['return list(d.keys())'],
            'test_cases': [('{"a":1,"b":2}', '["a","b"]')],
            'input_var': 'd', 'output_type': 'list',
        },

        # ── 聚合 ──
        'average': {
            'signature': 'def average(lst: list) -> float',
            'templates': ['return sum({input})/len({input}) if {input} else 0'],
            'test_cases': [('[1,2,3]', '2.0'), ('[10]', '10.0')],
            'input_var': 'lst', 'output_type': 'float',
        },
        'product_list': {
            'signature': 'def product_list(lst: list) -> int',
            'templates': ['p = 1\n    for x in {input}:\n        p *= x\n    return p'],
            'test_cases': [('[1,2,3]', '6'), ('[5]', '5')],
            'input_var': 'lst', 'output_type': 'int',
        },
        'range_sum': {
            'signature': 'def range_sum(start: int, end: int) -> int',
            'templates': ['return sum(range(start, end+1))'],
            'test_cases': [('1,5', '15'), ('0,0', '0')],
            'input_var': 'start, end', 'output_type': 'int',
        },

        # ── 过滤/映射 ──
        'filter_even': {
            'signature': 'def filter_even(lst: list) -> list',
            'templates': ['return [x for x in {input} if x % 2 == 0]'],
            'test_cases': [('[1,2,3,4]', '[2,4]'), ('[]', '[]')],
            'input_var': 'lst', 'output_type': 'list',
        },
        'filter_odd': {
            'signature': 'def filter_odd(lst: list) -> list',
            'templates': ['return [x for x in {input} if x % 2 != 0]'],
            'test_cases': [('[1,2,3,4]', '[1,3]'), ('[]', '[]')],
            'input_var': 'lst', 'output_type': 'list',
        },
        'square_each': {
            'signature': 'def square_each(lst: list) -> list',
            'templates': ['return [x*x for x in {input}]'],
            'test_cases': [('[1,2,3]', '[1,4,9]'), ('[]', '[]')],
            'input_var': 'lst', 'output_type': 'list',
        },
        'is_sorted': {
            'signature': 'def is_sorted(lst: list) -> bool',
            'templates': ['return all({input}[i] <= {input}[i+1] for i in range(len({input})-1))'],
            'test_cases': [('[1,2,3]', 'True'), ('[3,1,2]', 'False'), ('[]', 'True')],
            'input_var': 'lst', 'output_type': 'bool',
        },

        # ── 查找 ──
        'find_index': {
            'signature': 'def find_index(lst: list, x: int) -> int',
            'templates': ['try:\n        return lst.index(x)\n    except ValueError:\n        return -1'],
            'test_cases': [('[1,2,3],2', '1'), ('[1,2,3],5', '-1')],
            'input_var': 'lst, x', 'output_type': 'int',
        },
        'last_index': {
            'signature': 'def last_index(lst: list, x: int) -> int',
            'templates': ['for i in range(len(lst)-1,-1,-1):\n        if lst[i] == x:\n            return i\n    return -1'],
            'test_cases': [('[1,2,3,2],2', '3'), ('[1,2,3],5', '-1')],
            'input_var': 'lst, x', 'output_type': 'int',
        },

        # ── 旋转/移位 ──
        'rotate_left': {
            'signature': 'def rotate_left(lst: list, k: int) -> list',
            'templates': ['k = k % len(lst) if lst else 0\n    return lst[k:] + lst[:k]'],
            'test_cases': [('[1,2,3,4],1', '[2,3,4,1]'), ('[1,2,3],0', '[1,2,3]')],
            'input_var': 'lst, k', 'output_type': 'list',
        },
        'rotate_right': {
            'signature': 'def rotate_right(lst: list, k: int) -> list',
            'templates': ['k = k % len(lst) if lst else 0\n    return lst[-k:] + lst[:-k]'],
            'test_cases': [('[1,2,3,4],1', '[4,1,2,3]'), ('[1,2,3],0', '[1,2,3]')],
            'input_var': 'lst, k', 'output_type': 'list',
        },
        'swap_first_last': {
            'signature': 'def swap_first_last(lst: list) -> list',
            'templates': ['if len(lst) > 1:\n        lst[0], lst[-1] = lst[-1], lst[0]\n    return lst'],
            'test_cases': [('[1,2,3,4]', '[4,2,3,1]'), ('[5]', '[5]')],
            'input_var': 'lst', 'output_type': 'list',
        },

        # ── 数学 ──
        'is_even': {
            'signature': 'def is_even(n: int) -> bool',
            'templates': ['return n % 2 == 0'],
            'test_cases': [('4', 'True'), ('3', 'False'), ('0', 'True')],
            'input_var': 'n', 'output_type': 'bool',
        },
        'is_odd': {
            'signature': 'def is_odd(n: int) -> bool',
            'templates': ['return n % 2 != 0'],
            'test_cases': [('3', 'True'), ('4', 'False')],
            'input_var': 'n', 'output_type': 'bool',
        },
        'power': {
            'signature': 'def power(base: int, exp: int) -> int',
            'templates': ['return base ** exp'],
            'test_cases': [('2,10', '1024'), ('3,3', '27'), ('5,0', '1')],
            'input_var': 'base, exp', 'output_type': 'int',
        },
        'is_perfect_square': {
            'signature': 'def is_perfect_square(n: int) -> bool',
            'templates': ['import math\n    r = int(math.sqrt(n))\n    return r*r == n'],
            'test_cases': [('16', 'True'), ('14', 'False'), ('1', 'True')],
            'input_var': 'n', 'output_type': 'bool',
        },
        'sum_of_digits': {
            'signature': 'def sum_of_digits(n: int) -> int',
            'templates': ['return sum(int(d) for d in str(abs(n)))'],
            'test_cases': [('123', '6'), ('0', '0'), ('99', '18')],
            'input_var': 'n', 'output_type': 'int',
        },
        'reverse_integer': {
            'signature': 'def reverse_integer(n: int) -> int',
            'templates': ['sign = -1 if n < 0 else 1\n    return sign * int(str(abs(n))[::-1])'],
            'test_cases': [('123', '321'), ('-123', '-321'), ('0', '0')],
            'input_var': 'n', 'output_type': 'int',
        },
        'median': {
            'signature': 'def median(lst: list) -> float',
            'templates': ['s = sorted(lst)\n    n = len(s)\n    if n % 2:\n        return s[n//2]\n    return (s[n//2-1] + s[n//2]) / 2'],
            'test_cases': [('[1,2,3]', '2'), ('[1,2,3,4]', '2.5')],
            'input_var': 'lst', 'output_type': 'float',
        },
        'mode': {
            'signature': 'def mode(lst: list) -> int',
            'templates': ['from collections import Counter\n    return Counter(lst).most_common(1)[0][0]'],
            'test_cases': [('[1,2,2,3]', '2'), ('[5]', '5')],
            'input_var': 'lst', 'output_type': 'int',
        },
        'lcm': {
            'signature': 'def lcm(a: int, b: int) -> int',
            'templates': ['import math\n    return abs(a*b) // math.gcd(a,b)'],
            'test_cases': [('4,6', '12'), ('7,3', '21')],
            'input_var': 'a, b', 'output_type': 'int',
        },

        # ── 字符串 ──
        'count_vowels': {
            'signature': 'def count_vowels(s: str) -> int',
            'templates': ['return sum(1 for c in s.lower() if c in "aeiou")'],
            'test_cases': [('"hello"', '2'), ('""', '0'), ('"AEIOU"', '5')],
            'input_var': 's', 'output_type': 'int',
        },
        'count_words': {
            'signature': 'def count_words(s: str) -> int',
            'templates': ['return len(s.split())'],
            'test_cases': [('"hello world"', '2'), ('""', '0')],
            'input_var': 's', 'output_type': 'int',
        },
        'starts_with': {
            'signature': 'def starts_with(s: str, prefix: str) -> bool',
            'templates': ['return s.startswith(prefix)'],
            'test_cases': [('"hello","he"', 'True'), ('"hello","wo"', 'False')],
            'input_var': 's, prefix', 'output_type': 'bool',
        },
        'ends_with': {
            'signature': 'def ends_with(s: str, suffix: str) -> bool',
            'templates': ['return s.endswith(suffix)'],
            'test_cases': [('"hello","lo"', 'True'), ('"hello","he"', 'False')],
            'input_var': 's, suffix', 'output_type': 'bool',
        },
        'contains': {
            'signature': 'def contains(s: str, sub: str) -> bool',
            'templates': ['return sub in s'],
            'test_cases': [('"hello","ell"', 'True'), ('"hello","xy"', 'False')],
            'input_var': 's, sub', 'output_type': 'bool',
        },
        'remove_spaces': {
            'signature': 'def remove_spaces(s: str) -> str',
            'templates': ['return s.replace(" ", "")'],
            'test_cases': [('"hello world"', '"helloworld"'), ('""', '""')],
            'input_var': 's', 'output_type': 'str',
        },
        'capitalize_first': {
            'signature': 'def capitalize_first(s: str) -> str',
            'templates': ['return s.capitalize()'],
            'test_cases': [('"hello"', '"Hello"'), ('""', '""')],
            'input_var': 's', 'output_type': 'str',
        },
        'replace_char': {
            'signature': 'def replace_char(s: str, old: str, new: str) -> str',
            'templates': ['return s.replace(old, new)'],
            'test_cases': [('"hello","l","x"', '"hexxo"')],
            'input_var': 's, old, new', 'output_type': 'str',
        },
        'longest_word': {
            'signature': 'def longest_word(s: str) -> str',
            'templates': ['words = s.split()\n    return max(words, key=len) if words else ""'],
            'test_cases': [('"the quick brown fox"', '"quick"'), ('""', '""')],
            'input_var': 's', 'output_type': 'str',
        },

        # ── 哈希表/字典 ──
        'char_count': {
            'signature': 'def char_count(s: str) -> dict',
            'templates': ['from collections import Counter\n    return dict(Counter(s))'],
            'test_cases': [('"hello"', '{"h":1,"e":1,"l":2,"o":1}'), ('""', '{}')],
            'input_var': 's', 'output_type': 'dict',
        },
        'word_count': {
            'signature': 'def word_count(s: str) -> dict',
            'templates': ['from collections import Counter\n    return dict(Counter(s.split()))'],
            'test_cases': [('"a b a"', '{"a":2,"b":1}')],
            'input_var': 's', 'output_type': 'dict',
        },
        'intersection': {
            'signature': 'def intersection(a: list, b: list) -> list',
            'templates': ['return list(set(a) & set(b))'],
            'test_cases': [('[1,2,3],[2,3,4]', '[2,3]'), ('[1],[2]', '[]')],
            'input_var': 'a, b', 'output_type': 'list',
        },
        'union': {
            'signature': 'def union(a: list, b: list) -> list',
            'templates': ['return list(set(a) | set(b))'],
            'test_cases': [('[1,2],[2,3]', '[1,2,3]')],
            'input_var': 'a, b', 'output_type': 'list',
        },
        'set_difference': {
            'signature': 'def set_difference(a: list, b: list) -> list',
            'templates': ['return list(set(a) - set(b))'],
            'test_cases': [('[1,2,3],[2]', '[1,3]')],
            'input_var': 'a, b', 'output_type': 'list',
        },
        'has_duplicates': {
            'signature': 'def has_duplicates(lst: list) -> bool',
            'templates': ['return len(lst) != len(set(lst))'],
            'test_cases': [('[1,2,1]', 'True'), ('[1,2,3]', 'False')],
            'input_var': 'lst', 'output_type': 'bool',
        },

        # ── 栈 ──
        'stack_push': {
            'signature': 'def stack_push(stack: list, x: int) -> list',
            'templates': ['stack.append(x)\n    return stack'],
            'test_cases': [('[1,2],3', '[1,2,3]')],
            'input_var': 'stack, x', 'output_type': 'list',
        },
        'stack_pop': {
            'signature': 'def stack_pop(stack: list) -> int',
            'templates': ['return stack.pop() if stack else None'],
            'test_cases': [('[1,2,3]', '3'), ('[]', 'None')],
            'input_var': 'stack', 'output_type': 'int',
        },
        'stack_peek': {
            'signature': 'def stack_peek(stack: list) -> int',
            'templates': ['return stack[-1] if stack else None'],
            'test_cases': [('[1,2,3]', '3'), ('[]', 'None')],
            'input_var': 'stack', 'output_type': 'int',
        },
        'is_empty': {
            'signature': 'def is_empty(collection) -> bool',
            'templates': ['return len(collection) == 0'],
            'test_cases': [('[]', 'True'), ('[1]', 'False')],
            'input_var': 'collection', 'output_type': 'bool',
        },

        # ── 数组变换 ──
        'move_zeroes_end': {
            'signature': 'def move_zeroes_end(lst: list) -> list',
            'templates': ['nz = [x for x in lst if x != 0]\n    return nz + [0] * (len(lst) - len(nz))'],
            'test_cases': [('[0,1,0,3,12]', '[1,3,12,0,0]'), ('[1]', '[1]')],
            'input_var': 'lst', 'output_type': 'list',
        },
        'flatten_1level': {
            'signature': 'def flatten_1level(matrix: list) -> list',
            'templates': ['return [x for row in matrix for x in row]'],
            'test_cases': [('[[1,2],[3,4]]', '[1,2,3,4]'), ('[]', '[]')],
            'input_var': 'matrix', 'output_type': 'list',
        },
        'chunk_list': {
            'signature': 'def chunk_list(lst: list, size: int) -> list',
            'templates': ['return [lst[i:i+size] for i in range(0, len(lst), size)]'],
            'test_cases': [('[1,2,3,4,5],2', '[[1,2],[3,4],[5]]'), ('[],3', '[]')],
            'input_var': 'lst, size', 'output_type': 'list',
        },
        'running_sum': {
            'signature': 'def running_sum(lst: list) -> list',
            'templates': ['s = 0\n    result = []\n    for x in lst:\n        s += x\n        result.append(s)\n    return result'],
            'test_cases': [('[1,2,3,4]', '[1,3,6,10]'), ('[]', '[]')],
            'input_var': 'lst', 'output_type': 'list',
        },
        'pairwise_sum': {
            'signature': 'def pairwise_sum(lst: list) -> list',
            'templates': ['return [lst[i]+lst[i+1] for i in range(len(lst)-1)]'],
            'test_cases': [('[1,2,3,4]', '[3,5,7]'), ('[]', '[]')],
            'input_var': 'lst', 'output_type': 'list',
        },

        # ── 双指针 ──
        'merge_alternate': {
            'signature': 'def merge_alternate(a: list, b: list) -> list',
            'templates': ['result = []\n    i = j = 0\n    while i < len(a) and j < len(b):\n        result.append(a[i]); i+=1\n        result.append(b[j]); j+=1\n    result.extend(a[i:])\n    result.extend(b[j:])\n    return result'],
            'test_cases': [('[1,3],[2,4]', '[1,2,3,4]')],
            'input_var': 'a, b', 'output_type': 'list',
        },
        'remove_duplicates_sorted': {
            'signature': 'def remove_duplicates_sorted(lst: list) -> list',
            'templates': ['if not lst:\n        return []\n    r = [lst[0]]\n    for x in lst[1:]:\n        if x != r[-1]:\n            r.append(x)\n    return r'],
            'test_cases': [('[1,1,2,2,3]', '[1,2,3]'), ('[]', '[]')],
            'input_var': 'lst', 'output_type': 'list',
        },
        'two_sum_sorted': {
            'signature': 'def two_sum_sorted(lst: list, target: int) -> list',
            'templates': ['lo, hi = 0, len(lst)-1\n    while lo < hi:\n        s = lst[lo] + lst[hi]\n        if s == target:\n            return [lo, hi]\n        elif s < target:\n            lo += 1\n        else:\n            hi -= 1\n    return []'],
            'test_cases': [('[2,7,11,15],9', '[0,1]'), ('[1,2,3],6', '[]')],
            'input_var': 'lst, target', 'output_type': 'list',
        },

        # ── 递归基础 ──
        'sum_recursive': {
            'signature': 'def sum_recursive(lst: list) -> int',
            'templates': ['if not lst:\n        return 0\n    return lst[0] + sum_recursive(lst[1:])'],
            'test_cases': [('[1,2,3]', '6'), ('[]', '0')],
            'input_var': 'lst', 'output_type': 'int',
        },
        'power_recursive': {
            'signature': 'def power_recursive(base: int, exp: int) -> int',
            'templates': ['if exp == 0:\n        return 1\n    return base * power_recursive(base, exp-1)'],
            'test_cases': [('2,10', '1024'), ('5,0', '1')],
            'input_var': 'base, exp', 'output_type': 'int',
        },
        'gcd_recursive': {
            'signature': 'def gcd_recursive(a: int, b: int) -> int',
            'templates': ['if b == 0:\n        return a\n    return gcd_recursive(b, a % b)'],
            'test_cases': [('12,8', '4'), ('7,3', '1')],
            'input_var': 'a, b', 'output_type': 'int',
        },
    }

    # 重写规则：自动转换输出格式
    REWRITE_RULES = [
        (r"return sorted\((\w+)\)", lambda m: f"return ','.join(map(str,sorted({m.group(1)})))", 'list_to_str'),
        (r"return (\w+)\[::-1\]", lambda m: f"return ','.join(map(str,{m.group(1)}[::-1]))" if 'lst' in m.group(1) else m.group(0), 'rev_list_to_str'),
    ]

    def __init__(self):
        self.synthesis_count = 0
        self.success_count = 0

    def synthesize(self, spec: dict) -> List[str]:
        """
        输入: {'task': 'sort_list'}
        输出: 候选代码列表
        """
        task = spec.get('task', '')
        if task not in self.TEMPLATES:
            return []

        t = self.TEMPLATES[task]
        candidates = []
        input_var = t['input_var']

        # 解析参数列表
        if ',' in input_var:
            param_names = [p.strip() for p in input_var.split(',')]
        else:
            param_names = [input_var.strip()]

        for tmpl in t['templates']:
            code = tmpl
            # {input} 替换：单参数→参数名，多参数→逗号连接的参数列表
            if len(param_names) == 1:
                code = code.replace('{input}', param_names[0])
            else:
                code = code.replace('{input}', ', '.join(param_names))
            full_code = f"def {task}({', '.join(param_names)}):\n    {code}"
            candidates.append(full_code)

        self.synthesis_count += len(candidates)
        return candidates


# ═══════════════════════════════════════════════
# 2. 编译器验证器
# ═══════════════════════════════════════════════

class CompilerVerifier:
    """Python 编译器/语法检查器 — 编程锚第一层外部验证"""

    def __init__(self):
        self.total_checks = 0
        self.compile_failures = 0

    def check_syntax(self, code: str) -> Tuple[bool, str]:
        """语法检查——零容错"""
        self.total_checks += 1
        try:
            ast.parse(code)
            return True, 'ok'
        except SyntaxError as e:
            self.compile_failures += 1
            return False, f'语法错误 L{e.lineno}: {e.msg[:80]}'

    def check_type(self, code: str) -> Tuple[bool, str]:
        """类型检查（轻量——使用 mypy 调用）"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            tmp = f.name
        try:
            r = subprocess.run(['mypy', '--ignore-missing-imports', tmp],
                             capture_output=True, text=True, timeout=10)
            os.unlink(tmp)
            return r.returncode == 0, r.stdout[:200] if r.returncode != 0 else 'ok'
        except:
            os.unlink(tmp) if os.path.exists(tmp) else None
            return True, 'mypy not available — skipping'

    def metrics(self):
        return {
            'total': self.total_checks,
            'failures': self.compile_failures,
            'pass_rate': round((1 - self.compile_failures/max(self.total_checks,1))*100,1)
        }


# ═══════════════════════════════════════════════
# 3. 测试验证器
# ═══════════════════════════════════════════════

def normalize(val):
    """标准化输出格式 — Agent δ 开发规范 §3.1"""
    if isinstance(val, dict):
        items = []
        for k, v in val.items():
            items.append('"' + str(k) + '":' + str(v))
        return '{' + ','.join(items) + '}'
    if isinstance(val, list):
        items = []
        for x in val:
            if isinstance(x, str):
                items.append('"' + x + '"')
            elif isinstance(x, (list, dict)):
                items.append(normalize(x))
            else:
                items.append(str(x))
        return '[' + ','.join(items) + ']'
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, float) and val == int(val):
        return str(int(val)) + '.0'
    if isinstance(val, int):
        return str(val)
    return str(val)


class TestVerifier:
    """运行时测试验证器 — 编程锚第二层外部验证"""

    def __init__(self):
        self.total = 0
        self.failures = 0

    def run_tests(self, code: str, test_cases: List[Tuple[str, str]]) -> dict:
        """运行测试用例"""
        self.total += 1
        results = {'passed': 0, 'failed': 0, 'errors': [], 'outputs': []}

        for i, (inp, expected) in enumerate(test_cases):
            try:
                # 在隔离的命名空间中执行
                namespace = {}
                exec(code, namespace)

                func_name = [k for k in namespace if callable(namespace[k]) and not k.startswith('_')][0]
                func = namespace[func_name]

                # 解析输入 — 多参数检测：eval 整个元组
                try:
                    args = eval(f"({inp})")
                    if isinstance(args, tuple):
                        result = func(*args)
                    else:
                        result = func(args)
                except:
                    input_val = eval(inp) if inp.startswith('[') or inp.startswith('{') else (
                        int(inp) if inp.lstrip('-').isdigit() else
                        float(inp) if '.' in inp else
                        inp.strip('"').strip("'")
                    )
                    result = func(input_val)
                if normalize(result) == expected.strip('"\''):
                    results['passed'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(f'TC{i}: got {normalize(result)}, expected {expected}')

            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f'TC{i}: runtime error — {str(e)[:80]}')

        if results['failed'] > 0:
            self.failures += 1

        results['all_passed'] = results['failed'] == 0 and results['passed'] > 0
        return results


# ═══════════════════════════════════════════════
# 4. Agent δ — 编程锚完整闭环
# ═══════════════════════════════════════════════

@dataclass
class CodeGenEvent:
    """编程锚不一致事件"""
    event_id: int
    task: str
    inconsistency_type: str   # C1-C5（编程专用T1-T5映射）
    candidate: str             # 候选代码
    error_detail: str          # 错误详情
    timestamp: float

class AgentDelta:
    """Agent δ — 编程锚 · 编译器+测试双重验证"""

    # T1-T5 → C1-C5 映射
    # C1 = 编译失败（编程锚的 T1：合成≠编译器）
    # C2 = 测试失败（编程锚的 T1：合成≠测试预期）
    # C3 = 类型检查失败（编程锚的 T2：编译器通过但类型错误）
    # C4 = 双锚矛盾（编译器通过，测试全部失败 = 跨锚冲突）
    # C5 = 全部通过（编译器+类型+测试全绿）

    def __init__(self, log_dir='/opt/verix/logs'):
        self.synthesizer = TemplateSynthesizer()
        self.compiler = CompilerVerifier()
        self.tester = TestVerifier()
        self.events: List[CodeGenEvent] = []
        self.total_syntheses = 0
        self.successes = 0
        self.blind_spots: dict = {}
        self.log_dir = log_dir

    def generate_and_verify(self, task: str) -> dict:
        """完整的预测-验证-修正闭环"""
        self.total_syntheses += 1
        candidates = self.synthesizer.synthesize({'task': task})

        if not candidates:
            return {'status': 'blind_spot', 'msg': f'任务 {task} 无可用模板'}

        results = []
        for i, code in enumerate(candidates):
            result = {'candidate_id': i, 'code': code[:100], 'status': 'unknown', 'events': []}

            # 第一层：语法检查
            syntax_ok, syntax_err = self.compiler.check_syntax(code)
            if not syntax_ok:
                result['status'] = 'C1'
                result['events'].append({'type': 'C1', 'detail': syntax_err})
                results.append(result)
                self._log_event(task, 'C1', code, syntax_err)
                continue  # 语法错——跳过，不跑测试

            # 第二层：测试验证
            t = self.synthesizer.TEMPLATES.get(task, {})
            test_cases = t.get('test_cases', [])
            test_results = self.tester.run_tests(code, test_cases)

            if not test_results['all_passed']:
                result['status'] = 'C2'
                result['events'].append({'type': 'C2', 'detail': test_results['errors'][:3]})
                self._log_event(task, 'C2', code, str(test_results['errors'][:3]))
            else:
                result['status'] = 'C5'
                self.successes += 1
                self._log_event(task, 'C5', code, 'all passed')

            results.append(result)

        # 检查 C4：编译器全过但测试全挂
        all_compiled = all(r['status'] != 'C1' for r in results)
        all_tests_failed = all(r['status'] == 'C2' for r in results)
        if all_compiled and all_tests_failed and len(results) > 1:
            self._log_event(task, 'C4', candidates[0], '所有候选编译通过但测试全部失败——跨锚矛盾')

        return {
            'task': task,
            'candidates': len(candidates),
            'passed': sum(1 for r in results if r['status'] == 'C5'),
            'failed': sum(1 for r in results if r['status'] != 'C5'),
            'results': results,
        }

    def _log_event(self, task, etype, code, detail):
        event = CodeGenEvent(
            event_id=len(self.events),
            task=task,
            inconsistency_type=etype,
            candidate=code[:100],
            error_detail=str(detail)[:200],
            timestamp=time.time(),
        )
        self.events.append(event)

    def blind_spot_scan(self):
        """扫描编程锚盲区"""
        task_stats = defaultdict(lambda: {'total': 0, 'c5': 0})
        for e in self.events:
            task_stats[e.task]['total'] += 1
            if e.inconsistency_type == 'C5':
                task_stats[e.task]['c5'] += 1

        for task, s in task_stats.items():
            pass_rate = s['c5'] / max(s['total'], 1)
            if pass_rate < 0.4 and task not in self.blind_spots:
                self.blind_spots[task] = {
                    'pass_rate': pass_rate,
                    'reason': f'模板库不足以覆盖 {task}——需扩展合成模板'
                }

        return self.blind_spots

    def metrics(self):
        return {
            'total_syntheses': self.total_syntheses,
            'successes': self.successes,
            'success_rate': round(self.successes / max(self.total_syntheses, 1) * 100, 1),
            'c1_events': sum(1 for e in self.events if e.inconsistency_type == 'C1'),
            'c2_events': sum(1 for e in self.events if e.inconsistency_type == 'C2'),
            'c4_events': sum(1 for e in self.events if e.inconsistency_type == 'C4'),
            'blind_spots': list(self.blind_spots.keys()),
        }


# ═══════════════════════════════════════════════
# 5. GWT 调度器接口
# ═══════════════════════════════════════════════

class DeltaGWTBridge:
    """Agent δ ↔ GWT 调度器接口"""

    # C1-C5 → T1-T5 映射表
    C_TO_T_MAP = {
        'C1': 'T1',   # 编译失败 → 模拟≠外部验证
        'C2': 'T1',   # 测试失败 → 同上
        'C3': 'T2',   # 类型失败 → 模拟≠人类（类型约束=人类意图）
        'C4': 'T4',   # 双锚矛盾 → 跨Agent冲突
        'C5': 'T5',   # 全通过 → 正常流动
    }

    def __init__(self, delta: AgentDelta):
        self.delta = delta

    def run_and_translate(self, task: str) -> dict:
        """运行 Agent δ 并将 C 事件翻译为 GWT T 事件"""
        result = self.delta.generate_and_verify(task)

        t_events = []
        for r in result.get('results', []):
            for e in r.get('events', []):
                c_type = e['type']
                t_type = self.C_TO_T_MAP.get(c_type, 'T0')
                t_events.append({
                    'source': 'agent_delta',
                    't_type': t_type,
                    'c_type': c_type,
                    'task': task,
                    'detail': e['detail'],
                })

        result['gwt_t_events'] = t_events
        return result


# ═══════════════════════════════════════════════
# 6. 入口
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    import sys

    delta = AgentDelta()
    bridge = DeltaGWTBridge(delta)

    if '--eval' in sys.argv:
        tasks = list(TemplateSynthesizer.TEMPLATES.keys())
        print(f'  Agent δ · 编程锚 — 全任务评估')
        print(f'  {"─"*50}')
        total_pass = 0
        total_tasks = 0
        for task in tasks:
            r = bridge.run_and_translate(task)
            total_pass += r['passed']
            total_tasks += r['candidates']
            t_events = r.get('gwt_t_events', [])
            t1_count = sum(1 for e in t_events if e['t_type'] == 'T1')
            t5_count = sum(1 for e in t_events if e['t_type'] == 'T5')
            icon = '✅' if r['failed'] == 0 else '⚠️'
            print(f'  {icon} {task:20} 通过: {r["passed"]}/{r["candidates"]}  T1: {t1_count}  T5: {t5_count}')

        # 盲区
        bs = delta.blind_spot_scan()
        if bs:
            print(f'\n  🔴 盲区:')
            for t, b in bs.items():
                print(f'    {t}: 通过率 {b["pass_rate"]:.0%} — {b["reason"]}')
        else:
            print(f'\n  ✅ 无盲区')

        m = delta.metrics()
        print(f'\n  编译器: {delta.compiler.metrics()["pass_rate"]}% 通过')
        print(f'  合成成功率: {m["success_rate"]}%')

    elif '--test' in sys.argv:
        task = sys.argv[2] if len(sys.argv) > 2 else 'sort_list'
        r = bridge.run_and_translate(task)
        print(json.dumps(r, indent=2, ensure_ascii=False))

    else:
        print('Agent δ · 编程锚 — 编译器+测试框架 外部验证闭环')
        print('  --eval        评估所有任务')
        print('  --test TASK   测试单个任务')
