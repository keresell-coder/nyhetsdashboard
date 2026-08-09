#!/usr/bin/env python3
"""CLI-inngang for den daglige nyhetsscreeneren. All logikk ligger i src/;
se NEWS_SCREENER_SPEC.md for den redaksjonelle spesifikasjonen og planen i
repoet for arkitekturbegrunnelse.
"""

from src import pipeline

if __name__ == "__main__":
    pipeline.run()
