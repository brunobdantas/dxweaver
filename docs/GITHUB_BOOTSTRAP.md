# GitHub bootstrap — DXWeaver v0.3.0

The canonical repository is `https://github.com/brunobdantas/dxweaver.git`.

## PowerShell

```powershell
cd C:\path\to\dxweaver
git init
git branch -M main
git remote remove origin 2>$null
git remote add origin https://github.com/brunobdantas/dxweaver.git
git add .
git commit -m "feat: bootstrap DXWeaver v0.3.0"
git push -u origin main
```

## Bash

```bash
cd /path/to/dxweaver
git init
git branch -M main
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/brunobdantas/dxweaver.git
git add .
git commit -m "feat: bootstrap DXWeaver v0.3.0"
git push -u origin main
```

The repository includes `.github/workflows/windows-installer.yml`. Every push to
`main` builds and uploads the standalone installer as a GitHub Actions artifact.
Use **Actions → Windows Installer → Run workflow → publish_release=true** to
publish/update the `v0.3.0` GitHub Release.
