# LHAS JAIR Draft

Files:

- `lhas_jair.tex`: main manuscript draft in the JAIR template
- `lhas_refs.bib`: bibliography used by the manuscript

Suggested compile sequence:

```bash
latexmk -pdf lhas_jair.tex
```

or, if running manually:

```bash
pdflatex lhas_jair.tex
biber lhas_jair
pdflatex lhas_jair.tex
pdflatex lhas_jair.tex
```

Before submission, replace:

- author affiliation and email placeholders
- `\JAIRAE{}` metadata
- DOI / volume / article / month placeholders
- received / accepted dates as appropriate
- the JAIR Reference Format block with final bibliographic details

Recommended final packaging steps:

1. Add an explicit repository license if the code will be released with the paper.
2. Export an evaluation artifact bundle containing the mission telemetry used in the paper.
3. Recheck bibliography capitalization and venue formatting after the first successful LaTeX compile.
