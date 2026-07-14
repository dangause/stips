ROOTPATH := ../..
DEST_DIR := ../build

CSS := lick_archive_base dark_theme light_theme docs

all: frontend login docs_js $(CSS)

frontend: frontend.js data_dictionary config.json theme.js login_controls.js lick_archive_client.js error_section.js
	node ../build_scripts/build_js.mjs frontend.js $(DEST_DIR)/scripts/frontend.js

login: login.js login_controls.js lick_archive_client.js error_section.js
	mkdir -p ../build/scripts/
	node ../build_scripts/build_js.mjs login.js $(DEST_DIR)/scripts/login.js

docs_js: docs.js  login_controls.js lick_archive_client.js error_section.js
	mkdir -p ../build/scripts/
	node ../build_scripts/build_js.mjs docs.js $(DEST_DIR)/scripts/docs.js

data_dictionary:
	mkdir -p ../build/scripts/
	export PYTHONPATH=$(ROOTPATH);python $(ROOTPATH)/scripts/build_data_dictionary_json.py $(DEST_DIR)/scripts/data_dictionary.json

$(CSS):
	node ../build_scripts/build_css.mjs $(@).css $(DEST_DIR)/style/$(@).css

clean:
	rm -r ../build/scripts
	rm -r ../build/style
