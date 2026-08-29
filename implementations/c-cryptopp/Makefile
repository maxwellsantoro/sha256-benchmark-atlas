CXX ?= c++
CXXFLAGS ?= -O3 -Wall -Wextra -std=c++17
# Homebrew installs headers under $(brew --prefix cryptopp)/include/cryptopp;
# Debian/Ubuntu use crypto++/ via libcrypto++-dev.
BREW_PREFIX := $(shell brew --prefix cryptopp 2>/dev/null)
ifneq ($(BREW_PREFIX),)
  CXXFLAGS += -I$(BREW_PREFIX)/include
  LDFLAGS ?= -L$(BREW_PREFIX)/lib -lcryptopp
else
  PKG_CFLAGS := $(shell pkg-config --cflags libcrypto++ 2>/dev/null || pkg-config --cflags cryptopp 2>/dev/null)
  PKG_LIBS := $(shell pkg-config --libs libcrypto++ 2>/dev/null || pkg-config --libs cryptopp 2>/dev/null)
  CXXFLAGS += $(PKG_CFLAGS)
  LDFLAGS ?= $(if $(PKG_LIBS),$(PKG_LIBS),-lcryptopp)
endif

sha256_runner: sha256_runner.cpp
	$(CXX) $(CXXFLAGS) -o $@ $< $(LDFLAGS)

.PHONY: clean
clean:
	rm -f sha256_runner
