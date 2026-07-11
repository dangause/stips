ROOTPATH := ../..
DEST_DIR := ../build/html

all: index login

index: index_page.html.jinja archive_base_template.jinja
	mkdir -p $(DEST_DIR)
	python3 ../build_scripts/render_jinja_to_html.py index_page.html.jinja $(DEST_DIR)/index.html -v pagename=index -p ..

login: login_page.html.jinja archive_base_template.jinja
	mkdir -p $(DEST_DIR)
	python3 ../build_scripts/render_jinja_to_html.py login_page.html.jinja $(DEST_DIR)/login.html -v pagename=login -p ..

clean:
	rm -r $(DEST_DIR)
