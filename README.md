# Odos Areté: legal and support pages

The public Terms of Use, Privacy Policy, AI buddy disclosure, account deletion and support pages of the Odos Areté app, in English, Slovak and German.

Site: https://lordof2l.github.io/odos-arete-legal/

Plain HTML and one stylesheet, with no build step and no JavaScript. English is at the root, Slovak in `sk/`, German in `de/`. GitHub Pages serves the files as they are (`.nojekyll`). Every page shows its version and date at the bottom.

## Contact

Odos Areté is operated by Lukáš Litvák, an individual, Manzigenstrasse 1, 6067 Melchtal, Switzerland. Email lukasllitvak@gmail.com, phone +41 76 672 95 90.

## Check

`python3 check.py` (standard library only) checks every page in all three languages, its version and date, the operator contact and placeholders, then serves the site locally and follows every link within the site. Links to other sites are not fetched.
