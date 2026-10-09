
name: Auto Update GitHub Profile

on:
  schedule:
    - cron: "17 */6 * * *"

  workflow_dispatch:

  push:
    branches:
      - main
    paths:
      - "scripts/update_readme.py"
      - ".github/workflows/update-profile.yml"

permissions:
  contents: write

concurrency:
  group: update-profile
  cancel-in-progress: false

jobs:
  update-readme:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Update README
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python scripts/update_readme.py

      - name: Commit changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add README.md
          if ! git diff --cached --quiet; then
            git commit -m "chore: auto-update profile projects and skills"
            git push
          fi
