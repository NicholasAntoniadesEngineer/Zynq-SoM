# Occupancy cell-counter paired microbenchmark

Original base: `8a33a77b8250c1a254cb45dc80caa46f9eb5fd90`.
Candidate: that base plus the occupancy cell-counter patch (original patch SHA-256
`f0932b15f24fa7dad21077ef1aefbbaf0b08a7207b05aa2b2b1a1ac96b549bd4`).
Run from a repository containing the candidate sources. No CMake edits required.
For strict reproduction, use that exact base and patch, not subsequent occupancy changes.

The driver executes six serial alternating original/new pairs for each of counted
and null-sink modes. Each trial makes one million real `fits_hashed` calls after
untimed setup. It compares full receipt maps and geometry digests; it does not
instrument entries in the timed binaries. Expected counted receipt: 10,006,324
cell calls; expected digest: 14232918909567527723. The original observed pairs ran
under uncontrolled concurrent parent/agent load: no carrier latency inference.

Copy/paste commands (POSIX shell, C++17 compiler):

```sh
bench_tmp=$(mktemp -d /private/tmp/occupancy-counter-repro.XXXXXX)
mkdir -p "$bench_tmp/base/schgen"
git show 8a33a77b8250c1a254cb45dc80caa46f9eb5fd90:native/src/occupancy.cpp > "$bench_tmp/base/occupancy.cpp"
git show 8a33a77b8250c1a254cb45dc80caa46f9eb5fd90:native/src/occupancy_precision.cpp > "$bench_tmp/base/occupancy_precision.cpp"
git show 8a33a77b8250c1a254cb45dc80caa46f9eb5fd90:native/include/schgen/occupancy_precision.hpp > "$bench_tmp/base/schgen/occupancy_precision.hpp"
bench_src=native/benchmarks/occupancy_cell_counter
for variant in baseline candidate; do
    if [ "$variant" = baseline ]; then
        source_root="$bench_tmp/base"
        extra="-I$bench_tmp/base -Dschgen=baseline_schgen"
    else
        source_root=native/src
        extra=''
    fi
    for source in occupancy occupancy_precision; do
        c++ -std=c++17 -O3 -ffp-contract=off -Wall -Wextra -Wpedantic -Werror $extra -Inative/include -c "$source_root/$source.cpp" -o "$bench_tmp/$variant-$source.o"
    done
    c++ -std=c++17 -O3 -ffp-contract=off -Wall -Wextra -Wpedantic -Werror $extra -Inative/include -c native/src/quantize.cpp -o "$bench_tmp/$variant-quantize.o"
    c++ -std=c++17 -O3 -ffp-contract=off -Wall -Wextra -Wpedantic -Werror $extra -Inative/include -DENTRY="${variant}_run" -c "$bench_src/query_bench.cpp" -o "$bench_tmp/$variant-bench.o"
done
c++ -std=c++17 -O3 "$bench_src/bench_main.cpp" "$bench_tmp/baseline-occupancy.o" "$bench_tmp/baseline-occupancy_precision.o" "$bench_tmp/baseline-quantize.o" "$bench_tmp/baseline-bench.o" "$bench_tmp/candidate-occupancy.o" "$bench_tmp/candidate-occupancy_precision.o" "$bench_tmp/candidate-quantize.o" "$bench_tmp/candidate-bench.o" -o "$bench_tmp/query_bench"
"$bench_tmp/query_bench"
```

The old and new occupancy implementations are compiled into distinct namespaces,
with identical optimization flags. The three C++ files are the original measured
benchmark sources, not a replacement workload. No shell script is maintained.
