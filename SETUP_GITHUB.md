# GitHub Setup and ChatGPT Integration

The repository is designed so **GitHub is the canonical long-term home** while ZIP exports remain a vendor/account-independent handoff format.

Because the current ChatGPT account is not the user's main account, GitHub connection should be done later on the main account.

## 1. Create the GitHub repository

Recommended:

- create a **private** repository, e.g. `EE499-Team16`,
- do not make it public by default because the project contains team names, grades/feedback, meeting records, and original reports with student IDs,
- preferably create the GitHub repository empty (no generated README) if you plan to push this prepared folder directly.

## 2. Install Git LFS locally

This repository includes many binary Office/PDF/image files. `.gitattributes` is already prepared to keep common binary formats in Git LFS.

From the repository folder:

```bash
git lfs install
git init
git branch -M main
git add .
git commit -m "Organize EE499 Team 16 project repository"
git remote add origin <YOUR_PRIVATE_REPOSITORY_URL>
git push -u origin main
```

If the remote repository was created with an initial commit, clone it first and copy these files into the clone instead of blindly forcing histories together.

## 3. Connect GitHub on the main ChatGPT account

On the main ChatGPT account:

1. Open **Settings → Plugins** (or the Plugins area available in the current ChatGPT UI).
2. Find/install the **GitHub** plugin/connector.
3. Connect the GitHub account that can access the private repository.
4. During GitHub authorization, grant access to `EE499-Team16` (or the chosen repository).
5. In a new ChatGPT conversation, ask it to access the repository and verify it can see `README.md`.

The exact labels may change over time, but the essential steps are: install GitHub integration → authenticate → grant private-repository access → verify repository visibility.

## 4. Recommended first prompt on a new AI session

```text
Check the EE499 Team 16 repository. Read README.md first and follow AI_GUIDE.md.
If I am the primary repository user, also apply USER_PREFERENCES.md.
Give me only the short repository/project-state summary, then wait for my task.
```

After the short summary, give the specific chat task normally.

## 5. Disconnected-session workflow / ZIP handoff

GitHub access must never be required for working with the project. If the GitHub connector is not installed, not authorized, unavailable on an AI platform, or temporarily fails, **upload the latest full repository/handoff ZIP instead**.

The disconnected AI should not treat the ZIP as read-only reference material. It should:

1. read `README.md` and `AI_GUIDE.md`,
2. use the ZIP as the current working repository,
3. perform the same permitted repository/context edits that it would have made in a GitHub-connected session when the user's task calls for them,
4. return a **new complete updated ZIP** whenever persistent project changes were made,
5. tell the user that the new ZIP supersedes the uploaded snapshot for future disconnected sessions,
6. preserve meaningful feedback/state in the repository rather than leaving it only in chat when that feedback should carry forward.

Suggested prompt when using a ZIP:

```text
GitHub is not connected in this session. Treat the uploaded ZIP as the current working copy of the EE499 Team 16 repository. Read README.md first, follow AI_GUIDE.md and (for me) USER_PREFERENCES.md. If this session produces persistent project changes or feedback worth preserving, update the repository files and return a new complete ZIP at the end. Give me only the short project-state summary first, then wait for my task.
```

To build a normal portable handoff ZIP locally, run:

```bash
python tools/build_handoff.py
```

This creates a dated ZIP in `Exports/` containing the working repository but excluding `.git`, generated exports, caches, and temporary files. A ZIP returned by a disconnected AI can later be reconciled into GitHub; compare against any newer GitHub commits before replacing files.

## 6. Repository discipline

- Keep `02_Reports/Submitted/` immutable.
- Commit meaningful organizational/context changes along with the technical artifacts they describe.
- Do not commit API keys, passwords, tokens, or local environment secrets.
- Use `PROJECT_JOURNAL.md` for meaningful state events, not as a raw chat log.
- Use `DECISIONS.md` only for confirmed project decisions.


## 7. GitHub-ready ZIP

For a ZIP whose contents are laid out directly as the repository root, run:

```bash
python tools/build_github_ready.py
```

Extract that ZIP first. Then either drag the extracted files/folders into an empty **private** GitHub repository using the web UI, or initialize/push the extracted folder with Git. GitHub does not automatically unpack an uploaded ZIP into repository contents.
