import html
import json

from wikiglue.pagefacts import extract

BREED = """<html><head><style>dl{}</style></head><body>
<nav><dl><dt>Home</dt><dd>Menu</dd><dt>About</dt><dd>Us</dd></dl></nav>
<div class="summary"><dl>
  <div><dt><svg><path d="M1 1"/></svg><span>Size</span></dt><dd>Small</dd></div>
  <div><dt>Exercise</dt><dd>Up to 1 hour per day</dd></div>
  <div><dt>Coat length:</dt><dd>Short</dd></div>
</dl></div>
<table class="navbox"><tr><th>Hounds</th><td><a href="/a">Basset Hound</a> <a href="/b">Beagle</a></td></tr>
<tr><th>Terriers</th><td><a href="/c">Cairn Terrier</a> <a href="/d">Border Terrier</a></td></tr></table>
<table><tr><th>Age</th><th>Weight</th></tr><tr><td>8 weeks</td><td>1.5 kg</td></tr>
<tr><td>6 months</td><td>4 kg | approx</td></tr></table>
<footer><table><tr><td>Privacy</td></tr><tr><td>Cookies</td></tr></table></footer>
</body></html>"""


def test_recovers_lists_and_tables():
    out = extract(BREED, "The article text.")
    assert out == (
        "- **Size:** Small\n- **Exercise:** Up to 1 hour per day\n- **Coat length:** Short\n\n"
        "| Age | Weight |\n|---|---|\n| 8 weeks | 1.5 kg |\n| 6 months | 4 kg \\| approx |"
    )


def test_skips_what_the_article_already_has():
    article = "It is Small, needs Up to 1 hour per day, coat Short. At 8 weeks 1.5 kg, 6 months 4 kg | approx."
    assert extract(BREED, article) == ""


def test_tolerates_broken_html():
    assert extract("<dl><dt>A</dt><dd>one<dt>B<dd>two", "") == ""   # unclosed: nothing complete
    assert extract("", "") == ""


TRAITS = {"traits": {
    "family": {"traits": "Affectionate With Family", "score": 5, "selected": [], "description": "How affectionate a breed is.",
               "low": "Independent", "high": "Lovey-Dovey", "image": 204847},
    "dogs": {"traits": "Good With Other Dogs", "score": 4, "selected": [], "description": "How friendly to other dogs.",
             "low": "Not Recommended", "high": "Good With Other Dogs", "image": 204848},
    "coat": {"traits": "Coat Type", "score": 0, "selected": ["Smooth"], "description": "Coat types.",
             "low": "", "high": "", "image": 204849},
}}
MENU = [{"title": "Register a Dog", "image": 204838, "url": "/register"},
        {"title": "Breeder Toolkit", "image": 204818, "url": "/toolkit"},
        {"title": "Dog Training", "image": 204825, "url": "/training"}]
RATINGS = f"""<html><body>
<div class="mega-menu" data-menu='{json.dumps(MENU)}'>Register a Dog Breeder Toolkit Dog Training</div>
<div data-settings="{html.escape(json.dumps(TRAITS))}">
<h4>Affectionate With Family</h4><div class="score"></div><span>Independent</span><span>Lovey-Dovey</span>
<h4>Good With Other Dogs</h4><div class="score"></div><span>Not Recommended</span><span>Good With Other Dogs</span>
<h4>Coat Type</h4><span>Smooth</span><span>Wiry</span>
</div></body></html>"""
ARTICLE = ("IndependentLovey-Dovey How affectionate a breed is. "
           "How friendly to other dogs. Smooth Wiry Coat types.")


def test_recovers_values_from_embedded_json():
    assert extract(RATINGS, ARTICLE) == (
        "| traits | score | selected | low | high |\n|---|---|---|---|---|\n"
        "| Affectionate With Family | 5 |  | Independent | Lovey-Dovey |\n"
        "| Good With Other Dogs | 4 |  | Not Recommended | Good With Other Dogs |\n"
        "| Coat Type | 0 | Smooth |  |  |"
    )


def test_skips_json_unrelated_to_the_article():
    # The menu's only numbers are ids; the ratings share no text with this article.
    assert extract(RATINGS, "Something else entirely.") == ""
