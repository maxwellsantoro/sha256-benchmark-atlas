ZIG ?= zig

sha256_runner.wasm: sha256_runner.c
	$(ZIG) cc -target wasm32-wasi -O3 -o $@ $<

sha256_runner: sha256_runner.wasm run.sh
	cp run.sh $@
	chmod +x $@

.PHONY: clean
clean:
	rm -f sha256_runner sha256_runner.wasm
