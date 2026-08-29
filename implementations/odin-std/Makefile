ODIN ?= odin

sha256_runner: sha256_runner.odin
	$(ODIN) build sha256_runner.odin -file -out:$@ -o:speed

.PHONY: clean
clean:
	rm -f sha256_runner
