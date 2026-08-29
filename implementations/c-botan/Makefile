CC ?= cc
CFLAGS ?= -O3 -Wall -Wextra
# Ubuntu packages Botan 2 as botan-2; Botan 3 uses botan-3.
PKG_CFLAGS := $(shell pkg-config --cflags botan-3 2>/dev/null || pkg-config --cflags botan-2 2>/dev/null)
PKG_LIBS := $(shell pkg-config --libs botan-3 2>/dev/null || pkg-config --libs botan-2 2>/dev/null)
LDFLAGS ?= $(if $(PKG_LIBS),$(PKG_LIBS),-lbotan-2)
CFLAGS += $(PKG_CFLAGS)

sha256_runner: sha256_runner.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

.PHONY: clean
clean:
	rm -f sha256_runner
