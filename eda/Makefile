.PHONY: install install-dev test clean lint

# Hatchling's editable install marks its .pth file with macOS UF_HIDDEN +
# com.apple.provenance xattr; Python 3.13+ refuses to load hidden .pth files.
# We strip both as a post-install step.
SITE_PKGS := $$(python -c 'import site; print(site.getsitepackages()[0])')

install:
	pip install -e . --config-settings editable_mode=compat
	@find $(SITE_PKGS) -name "*zynq_eda*.pth" -exec chflags nohidden {} \; 2>/dev/null || true
	@find $(SITE_PKGS) -name "*zynq_eda*.pth" -exec xattr -c {} \; 2>/dev/null || true
	@python -c "import zynq_eda; print(f'OK: zynq_eda {zynq_eda.__version__} importable')"

install-dev: install
	pip install -e '.[dev]' --config-settings editable_mode=compat

test:
	pytest tests -v

lint:
	ruff check src tests

clean:
	rm -rf build dist src/*.egg-info
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -exec rm -rf {} + 2>/dev/null || true
