SWIFT ?= swiftc

sha256_runner: main.swift
	$(SWIFT) -O -parse-as-library -o $@ main.swift 2>/dev/null || $(SWIFT) -O -o $@ main.swift

.PHONY: clean
clean:
	rm -f sha256_runner
