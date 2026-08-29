CC ?= cc
CFLAGS ?= -O3 -Wall -Wextra
# Prefer an explicit LibreSSL prefix so we do not accidentally link stock OpenSSL.
LIBRESSL_PREFIX ?= $(shell brew --prefix libressl 2>/dev/null)
ifeq ($(LIBRESSL_PREFIX),)
  PKG_CFLAGS := $(shell pkg-config --cflags libressl 2>/dev/null)
  PKG_LIBS := $(shell pkg-config --libs libressl 2>/dev/null)
else
  PKG_CFLAGS := -I$(LIBRESSL_PREFIX)/include
  PKG_LIBS := -L$(LIBRESSL_PREFIX)/lib -lcrypto
endif
ifeq ($(PKG_LIBS),)
  $(error LibreSSL not found. Set LIBRESSL_PREFIX or install libressl / pkg-config libressl)
endif
CFLAGS += $(PKG_CFLAGS)
LDFLAGS ?= $(PKG_LIBS)

sha256_runner: sha256_runner.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

.PHONY: clean
clean:
	rm -f sha256_runner
