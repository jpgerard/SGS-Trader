"""
Allow running SGS CLI as a module: python -m sgs
"""

from sgs.cli import cli

if __name__ == '__main__':
    cli()
