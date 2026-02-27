# Veelgebruikte Git-commando's in deze repo

| **#** | **command** | **definition** |
| --- | --- | --- |
| **1** | git checkout main | Ga terug naar de hoofdbranch. |
| **2** | git pull origin main | Download de laatste code van github naar je lokale machine. |
| **3** | git checkout -b \<branch-naam\> | Maak een nieuwe branch aan én switch er direct naartoe. |
| **4** | git status | Bekijk welke bestanden zijn gewijzigd, toegevoegd of klaargezet (altijd doen voor een commit!). |
| **5** | git add \<bestand/map\> | Zet specifieke bestanden klaar om te committen. |
| **6** | git add . | Zet alle gewijzigde bestanden in de huidige map klaar. |
| **7** | git commit -m "\<bericht\>" | Commit met een message. |
| **8** | git push origin \<branch-naam\> | Stuur je lokale branch naar GitHub (bijv. om een Pull Request aan te maken). |
| **9** | git reset HEAD~1 | Verwijder de laatste commit, maar behoud al je getypte code lokaal. |
| **10** | git reset --hard HEAD~1 | GEVAARLIJK: Verwijder de laatste commit én vernietig de bijbehorende code definitief. |
| **11** | git restore \<bestand\> | Wis alle niet-opgeslagen wijzigingen in een bestand en zet het terug naar de originele staat. |
| **12** | git diff | Laat exact regel voor regel zien wat je hebt aangepast sinds je laatste save. |
| **13** | git branch -d \<branch-naam\> | Verwijder een lokale branch VEILIG (Git blokkeert dit als de branch nog niet is gemerged). |
| **14** | git branch -D \<branch-naam\> | Verwijder een lokale branch GEFORCEERD (Gooit de branch weg, ongeacht of de code is gemerged of niet). |
