SUBDIRS:= doc src templates

all: node_modules $(SUBDIRS)
clean: $(SUBDIRS) clean_node_modules


.PHONY: $(SUBDIRS)
$(SUBDIRS):
	$(MAKE) -C $@ $(MAKECMDGOALS)

node_modules:
	npm install --save-exact --save-dev esbuild

clean_node_modules:
	rm -r node_modules
