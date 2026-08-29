CC ?= cc
CFLAGS ?= -O3 -Wall -Wextra
PKG_CFLAGS := $(shell pkg-config --cflags nss 2>/dev/null)
PKG_LIBS := $(shell pkg-config --libs nss 2>/dev/null)
LDFLAGS ?= $(if $(PKG_LIBS),$(PKG_LIBS),-lnss3 -lnspr4)
CFLAGS += $(PKG_CFLAGS)

sha256_runner: sha256_runner.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

.PHONY: clean
clean:
	rm -f sha256_runner
