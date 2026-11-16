# Build the SDC-V technical report.  make pdf | make clean | make distclean
# Uses latexmk when it is installed; otherwise falls back to pdflatex + bibtex (three passes).
MAIN := main
LATEXMK := $(shell command -v latexmk 2>/dev/null)

.PHONY: pdf clean distclean example

pdf:
ifdef LATEXMK
	latexmk -pdf -interaction=nonstopmode -halt-on-error $(MAIN).tex
else
	pdflatex -interaction=nonstopmode -halt-on-error $(MAIN).tex
	bibtex $(MAIN)
	pdflatex -interaction=nonstopmode -halt-on-error $(MAIN).tex
	pdflatex -interaction=nonstopmode -halt-on-error $(MAIN).tex
endif

# Regenerate the worked example (Appendix C) from the real calculator.
example:
	python3 -I tools/gen_example.py

clean:
ifdef LATEXMK
	latexmk -c $(MAIN).tex
endif
	rm -f $(MAIN).aux $(MAIN).bbl $(MAIN).blg $(MAIN).log $(MAIN).out $(MAIN).toc $(MAIN).lof $(MAIN).lot \
	      $(MAIN).fls $(MAIN).fdb_latexmk $(MAIN).synctex.gz

distclean: clean
	rm -f $(MAIN).pdf
