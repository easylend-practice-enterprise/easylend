# Frequently Used Git Commands in This Repo

| **#** | **command** | **definition** |
| --- | --- | --- |
| **1** | git checkout main | Switch back to the main branch. |
| **2** | git pull origin main | Download the latest code from GitHub to your local machine. |
| **3** | git checkout -b \<branch-name\> | Create a new branch and switch to it immediately. |
| **4** | git status | View which files have been changed, added, or staged (always do this before committing!). |
| **5** | git add \<file/folder\> | Stage specific files for commit. |
| **6** | git add . | Stage all changed files in the current directory. |
| **7** | git commit -m "\<message\>" | Commit with a message. |
| **8** | git push origin \<branch-name\> | Push your local branch to GitHub (e.g. to open a Pull Request). |
| **9** | git reset HEAD~1 | Remove the last commit but keep all your code changes locally. |
| **10** | git reset --hard HEAD~1 | DANGEROUS: Remove the last commit and permanently destroy the associated code. |
| **11** | git restore \<file\> | Discard all unsaved changes in a file and restore it to its original state. |
| **12** | git diff | Show exactly line by line what you have changed since your last save. |
| **13** | git branch -d \<branch-name\> | Delete a local branch SAFELY (Git blocks this if the branch is not yet merged). |
| **14** | git branch -D \<branch-name\> | Delete a local branch FORCEFULLY (discards the branch regardless of whether the code is merged or not). |
