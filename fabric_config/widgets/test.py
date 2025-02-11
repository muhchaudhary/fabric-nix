import math
def solve(n):
  if n == 0:
    return 0
  rev_n = 0
  curr_mod = 10
  negative = -1 if n < 0 else 1
  n = abs(n)
  n_digits = int(math.log(n,10))
  while True:
    x = n % curr_mod
    rev_n += (x // (curr_mod // 10)) * (10 ** n_digits)

    if n_digits == 0:
      return rev_n * negative

    curr_mod *= 10
    n_digits -= 1

print(solve(1534236469))

