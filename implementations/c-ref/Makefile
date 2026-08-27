CC ?= cc
CFLAGS ?= -O3 -Wall -Wextra

sha256_runner: sha256_runner.c
	$(CC) $(CFLAGS) -o $@ $<

.PHONY: clean
clean:
	rm -f sha256_runner
