# Numerical reliability correction

Base: `6a580efe447c2bf02f30a0ffe5fe54700a66e3ec`. Private implementation and
validation; no shared checkout changes, builds, generated boards or fixtures.

## Decisions and reproduced defects

1. `outline_snap_up(1e12)`, `outline_snap_up(infinity)` and
   `outline_snap_up(NaN)` execute an undefined floating-to-int conversion in
   the original `quantize.cpp`. Clang's float-cast-overflow sanitizer reproduces
   it at the conversion. Replace the integer intermediate with floating
   truncation; explicitly reject nonfinite input or result. Retain the precise
   addition/subtraction/division order, truncation toward zero, 1e-6 bias and
   positive-zero behavior. This is NOT a change to mathematical ceiling or to
   the physical 5 mm policy. Finite values beyond the former int range now use
   the same formula without undefined behavior. For example, 1e12 produces
   1000000000005 because the formula's subtraction of 1e-6 rounds away at that
   magnitude. Changing that historical formula would be a separate policy
   decision. (Autonomous, per full-autonomy directive.)
2. `accurate_hypot2` rounds a scaled square root to binary64 before rescaling
   into the subnormal range, causing double rounding. Exact input example:
   `0x1.edc9cd02eb226p-1023`, `0x1.40e6a86941c2p-1027`; original output
   `0x1.ee3207de7815p-1023`, independently correctly rounded output
   `0x1.ee3207de7814ep-1023`. An initial million-pair MPFR scan (half subnormal,
   seed 83476) reproduced 84,517 mismatches. The correction computes the exact
   integer squared sum in denormal units when both components are at most the
   smallest normal value. If n is its integer square root, round upward iff
   S - n*n > n. No exact halfway case exists since (n+1/2)^2 is nonintegral.
   The floating sqrt only seeds a checked integer square-root search. The
   resulting integer has at most 53 bits and rescaling is exact. The ordinary
   norm path and nonfinite classification are unchanged. This intentionally
   corrects inaccurate historical outputs in this narrow tiny-input domain.
   (Autonomous, per full-autonomy directive.)

`occupancy.cpp::py_round` was reviewed and independently tested; it is NOT
changed. Its existing 0..15 digits / 2^53 decimal-unit bound remains intact.
No policy constants, tolerances, gates, accounting, or fixtures are modified.

## Facing-angle extension

The combined patch supersedes the original six-file patch and still applies
directly to `6a580efe`. The extension affects only `accurate_norm.hpp`,
`numeric_contracts.cpp`, this report, and the optional MPFR oracle.

Against the original header extracted from `6a580efe`, a standalone negative
test reproduces all of these failures (M = maximum finite binary64):

- `facing(0,0,1e200,1e200,-1e200,1e200)`: angle 0 instead of 90 degrees.
- `facing(0,0,M,M,1e-8,0)`: angle 90 instead of 45 degrees, even though the
  dot product is finite; the norm alone overflows.
- `facing(0,0,2^520,2^520,2^520,nextafter(-2^520,0))`: NaN dot instead of
  exactly 2^987 because the individual products overflow before cancellation.
- `facing(-M,0,M,M,-M,M)`: angle 0 instead of about 63.434948822922 degrees;
  finite coordinates overflow during subtraction.
- An infinite coordinate can produce angle 0. Invalid geometry was silently
  turned into a valid-looking angle by the min/max NaN clamp.

The ordinary finite-intermediate path retains the exact old expressions and
rounding, verified with 100,000 parity cases and unchanged existing fixtures.
Only finite overflow engages the new fallback: represent displacement
components with separate power-of-two exponents; preserve product and sum
errors with FMA/TwoSum; calculate an angle with atan2(abs(determinant),dot).
Separate component scales retain significant products such as 1e308 * 1e-308
that a common vector scale can erase. Subtraction overflow uses halved finite
endpoints with a separately retained factor of two. It does not rely on
platform-dependent extended precision or introduce a library dependency.

The dot result is finite where representable, zero for exact cancellation, or
signed infinity where its magnitude exceeds binary64. An overflowing dot or
norm no longer prevents a finite meaningful angle. The unchanged <=1e-9
degenerate-vector rule still returns 180 degrees, including subnormals and
mixed huge/tiny vectors. All NaN/infinite input coordinates explicitly return
NaN for BOTH outputs. That narrowly justified invalid-input correction is
distinct from recovering valid finite inputs. No epsilon or physical policy
changes are made. (Autonomous, per explicit facing-angle accuracy request.)

The angular oracle uses MPFR at 4608 bits, sufficient for exact coordinate
differences/products over the binary64 exponent span, and independent atan2
and pi conversion. It checks 5,714 cases: high/high, high/low in both orders,
degenerate lows, nextafter threshold neighbors, near-parallel/antiparallel,
finite cancellation of overflowing products, component-scale imbalance,
and large translated coordinates. The independent angular error budget is
5e-13 degrees (a test bound, not a design tolerance). Dot results for origin-zero
cases must agree within two ULPs, including overflow sign and exact zeros.
The test suite does not claim universally correctly rounded angles or dots;
the existing ordinary acos path and its near-parallel conditioning remain
unchanged by this scoped overflow correction.

## Validation

Apple clang 21.0.0, arm64 macOS, C++17. The existing `numeric_contracts.cpp`
CTest target now covers the regressions without a new runtime dependency:

- Five exact hexadecimal norm regressions, both signs and permutations.
- Exact 3-4-5 and axis identities at every exponent -1074 through 1020.
- Subnormal/normal transitions, signed zero, infinity, NaN, norm overflow.
- Outline bias and negative inputs, signed zero, both int boundaries and
  formerly undefined large dimensions, plus nonfinite rejection.
- 100,000 finite outline inputs checked against the old expression ONLY where
  its int conversion is defined (historical parity, not an accuracy oracle).
- Existing decimal rounding and s-expression contracts.

All pass in optimized builds both with default contraction and with
`-ffp-contract=off`, and with ASan + UBSan + float-cast-overflow,
`-fno-sanitize-recover=all`. `legalize_precision_contracts` passes its unchanged
fixture; `compose_kernel_contracts` passes all 257 comparisons.

The optional `numerical_oracle.cpp` uses MPFR at 256 bits for scalar tests. It passes 1,000,000
norm pairs (500,000 subnormal, plus branch-boundary and full exponent coverage),
232,639 supported decimal rounds, 17,361 expected cap rejections and 100,000
outline expressions, plus the angular tests above at 4608 bits. It also passes ASan + UBSan + float-cast-overflow.
MPFR/GMP themselves are prebuilt and not sanitizer-instrumented. This is
independent numeric evidence, not a proof for all normal-range norm inputs.

From a private repo copy on this validation host:

```sh
clang++ -std=c++17 -O2 -ffp-contract=off -Wall -Wextra -Wpedantic -Werror \
  -I native/include native/tests/numeric_contracts.cpp \
  native/src/quantize.cpp native/src/occupancy.cpp \
  native/src/occupancy_precision.cpp native/src/sexpr.cpp \
  -Wl,-dead_strip -o /private/tmp/numeric-contracts
/private/tmp/numeric-contracts

clang++ -std=c++17 -O2 -ffp-contract=off -Wall -Wextra -Wpedantic -Werror \
  -I native/include -I /opt/homebrew/opt/mpfr/include \
  -I /opt/homebrew/opt/gmp/include native/tests/numerical_oracle.cpp \
  native/src/quantize.cpp native/src/occupancy.cpp \
  native/src/occupancy_precision.cpp -L /opt/homebrew/opt/mpfr/lib \
  -lmpfr -Wl,-dead_strip -o /private/tmp/numerical-oracle
/private/tmp/numerical-oracle
```

For sanitizer reproduction, replace `-O2` with
`-O1 -g -fsanitize=address,undefined,float-cast-overflow -fno-sanitize-recover=all`.
Other hosts need their MPFR/GMP include/library locations and platform linker
flags; this optional oracle is not added as a required product dependency.

## Remaining concerns and integration scope

The existing `__int128` compiler requirement also applies to the new exact
tiny-norm branch. No new platform dependency is introduced into the product.
The default floating environment (round-to-nearest, gradual underflow) is the
tested environment; arbitrary external floating-environment mutation is not
covered. Full board generation, electrical/visual gates, whole-program
sanitizers, and source-policy audits were not run here. The parent must run
those on the merged result; this scoped patch is not a board-completion claim.
