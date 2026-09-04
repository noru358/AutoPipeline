# AutoPipeline

Parent superproject for reusable content-production automation.

Child projects remain independent Git repositories and creative authorities.

Current children:
- instatoon -> noru358/instatoon
- talkshow -> noru358/talkshow

Use Git submodules so this repository records the exact child commit combination without copying child history.

Clone:
git clone --recurse-submodules <repo>

Restore:
git submodule update --init --recursive
