<div align="center">
  <img src="static/img/logo.svg" alt="Buckezz Logo" width="300"/>
  
  <h3>Buckezz 2.0 — One Bucket for Everything.</h3>
  <p>Moderne, konfigurierbare Progressive Web App (PWA) für smarte Listen-, Sammlungs-, Event-, Tracker- und To-Do-Verwaltung mit eigenem Vorlagen-Studio, KI-Assistent, Alexa-Sprachsteuerung und reisesicherer Kalendersynchronisation.</p>
</div>

---

## 🌟 Features in Buckezz 2.0

*   **Design Studio & Bootstrap 5 UI:** Zentrales Theme-System (`django-design-studio`) für Farben, Typografie, Hell-/Dunkelmodus, Navigations-Layout und einfärbbare Design-Icons (`bi-*`) sowie Emojis.
*   **Vorlagen-Studio (No-Code Builder):** Eigene Vorlagen per Drag & Drop zusammenstellen – inklusive Status-Workflows (`allowed_statuses_json`), Personen-Rollen (`allowed_roles_json`), Zusatzfeldern (Text, Zahl, Währung mit Kürzel, Datum, URL, Bild, Dropdown, Umfrage Einfach-/Mehrfachauswahl, Checkbox, Bewertung, Farbe), Gruppierung, KPI-Auswertung (mit Status-Filter), Wiederkehr-Automatik und Live-Vorschau.
*   **KI-Vorlagen-Assistent (Gemini):** App-Idee kurz beschreiben, fertigen Schema-Prompt kopieren und das erzeugte JSON per Drag & Drop importieren – inklusive automatischer Anlage von Vorlage, Liste und Beispiel-Einträgen.
*   **Flexible Ansichten & Plausibilitäts-Checks:** Pro Liste umschaltbar zwischen **Zeile**, **Karten-Grid** (`1/4`, `1/2`, `3/4`, `1 Hero`) und **Detail-Stapel** (wird in der Session gemerkt), Quick-Button *„1 Tag vor Ende“* für Erinnerungen sowie nicht-blockierende Plausibilitätshinweise bei Status- und Rollenwechseln.
*   **Mobile-First & PWA:** Responsive Layouts für Desktop und Smartphone, installierbar als App auf dem Homescreen.
*   **Smarte Standard-Vorlagen:** Einkaufsliste, To-Do, Weinvorrat, Veranstaltungsplaner, Medikamentenplan, Wunschliste (inkl. Wichtel-Modus), Haustier-Planer, Pflanzen-Pflege, Bucket List, Arzt-Termine, Trainingsplan (Gym Cockpit), Geliehen & Verliehen sowie Kalorien- & Gewichtstracker.
*   **📧 Intelligente E-Mail-Erinnerungen:** Automatisierte Erinnerungs-Mails mit Echtzeit-Status-Badges (`Erinnerung geplant` / `(gesendet)`).
*   **🌍 Reisesicherer Zeitzonen-Sync & Outlook-Fix (Hybrid-Engine):**
    *   **Im Browser:** Automatische Zeitzonen-Erkennung über das Cookie `django_timezone`.
    *   **Im Kalender (Outlook, Google Calendar, Apple):** iCal-Abonnements (`.ics`) mit einstellbarer **Heimat-Zeitzone** und `TZID`-Parameter (verhindert den Outlook-DST-Versatz).
*   **🎙️ Smart Alexa Integration:** Deutscher NLP-Parser für Spracheingaben (Bezeichnung, Menge, Marke, Geschäft, Preis) inkl. Multi-User-Routing.

---

## 🛠️ Technologie-Stack

*   **Backend:** Python 3.13 / Django 6.x
*   **Datenbank:** SQLite 3 (persistent über Docker-Volume angebunden)
*   **Frontend:** Bootstrap 5, `django-design-studio`, HTMX (Teil-Seiten-Updates), Alpine.js (reaktive UI-Komponenten), SortableJS, Tom Select
*   **Kalender:** RFC 5545 iCalendar Feeds / FullCalendar
*   **Server / Deployment:** Gunicorn / WhiteNoise (Statische Dateien), Docker Compose

---

## 🚀 Installation & Deployment (Server / NAS)

Die App ist für den reibungslosen Betrieb über Docker Compose konzipiert.

### 1. Die Konfigurationsdatei `.env` erstellen
Erstelle im Hauptverzeichnis deines Servers/NAS eine Datei namens `.env` und befülle sie mit deinen Konfigurationsdaten. Hier ist eine ausführliche Übersicht aller verfügbaren Variablen:

```env
# --- Django Basis-Einstellungen ---
SECRET_KEY=dein-super-geheimes-django-secret-key  # Einzigartiger, geheimer Schlüssel zur Absicherung der Sessions
DEBUG=False                                      # Im Produktivbetrieb IMMER False für optimale Performance & Sicherheit
ALLOWED_HOSTS=localhost,127.0.0.1,deine-domain.de # Komma-separierte Liste von Hostnames/IPs, unter denen die App erreichbar ist
CSRF_TRUSTED_ORIGINS=https://deine-domain.de      # Erforderlich für Formular-Absendungen über HTTPS-Domains

# --- Datenbank-Pfad ---
DB_PATH=/app/data/db.sqlite3                      # Der Pfad zur SQLite-Datenbank innerhalb des Docker-Containers

# --- E-Mail (SMTP) Einstellungen für Erinnerungen ---
EMAIL_HOST=smtp.dein-anbieter.de                 # Dein SMTP-Mailserver (z. B. smtp.strato.de, mail.gmx.net)
EMAIL_PORT=587                                   # Port deines SMTP-Servers (üblicherweise 587 bei TLS, 465 bei SSL)
EMAIL_USE_TLS=True                               # Nutze TLS-Verschlüsselung (empfohlen bei Port 587)
EMAIL_HOST_USER=deine-email@anbieter.de          # Benutzername für deinen E-Mail-Account
EMAIL_HOST_PASSWORD=dein-smtp-passwort           # Passwort (oder App-Passwort) deines E-Mail-Accounts
DEFAULT_FROM_EMAIL=Buckezz <noreply@deine-domain.de> # Der Absendername der Erinnerungs-Mails

# --- Docker Compose Variablen ---
WEB_PORT=8006                                    # Der Port auf dem Host-System, unter dem Buckezz erreichbar sein soll
CONTAINER_NAME=buckezz_web                       # Name des laufenden Docker-Containers
IMAGE_NAME=buckezz_image                         # Name des gebauten Docker-Images
DB_DIR=./data                                    # Lokales Verzeichnis auf dem Host zur Speicherung der Datenbank
```

### 2. Erstinstallation (Automated Setup)
Führe das mitgelieferte Installationsskript aus. Es kümmert sich um den Docker-Build, Datenbank-Migrationen, das Einsammeln statischer Dateien und das Einrichten der Standard-Listen-Vorlagen:

```bash
chmod +x docker/install.sh
./docker/install.sh
```

### 3. Administrator-Konto erstellen
Um dich im System und im Django-Admin-Bereich einloggen zu können, erstelle ein Superuser-Konto:

```bash
docker compose exec web python manage.py createsuperuser
```

---

## ⏰ E-Mail-Erinnerungen auf Synology NAS automatisieren

Um den regelmäßigen Versand der E-Mail-Erinnerungen sicherzustellen, richten wir auf der Synology NAS einen automatisierten Cronjob über den **DSM Aufgabenplaner** ein:

1. Öffne die **Systemsteuerung** auf deiner Synology NAS und navigiere zu **Aufgabenplaner**.
2. Klicke auf **Erstellen** > **Geplante Aufgabe** > **Benutzerdefiniertes Skript**.
3. **Reiter "Allgemein":**
   * **Aufgabe:** `Buckezz E-Mail Erinnerungen`
   * **Benutzer:** **`root`** (Dies ist zwingend notwendig, da der Cronjob die Berechtigung benötigt, Docker-Befehle auf dem System auszuführen!)
   * Aktiviere das Häkchen bei *Aktiviert*.
4. **Reiter "Zeitplan":**
   * **Ausführen an folgenden Tagen:** Täglich
   * **Frequenz:** Ausführen alle **15 Minuten** (oder kürzer/länger, je nach gewünschter Präzision deiner Erinnerungen).
5. **Reiter "Aufgabeneinstellungen":**
   * Gib unter **Benutzerdefiniertes Skript** exakt folgenden Befehl ein:
     ```bash
     docker exec buckezz_web python manage.py send_reminders
     ```
   * *Tipp:* Aktiviere *"Ergebnisse über E-Mail senden"* und trage deine E-Mail-Adresse ein, um im Fehlerfall sofort benachrichtigt zu werden.

---

## 🌍 Zeitzonen & iCal Outlook-Synchronisation (Deep-Dive)

To-Dos und Erinnerungen hängen stark von der Zeitzonen-Genauigkeit ab. Buckezz verwendet ein ausgeklügeltes Zeitzonen-Handling, um Fehler im In- und Ausland komplett auszuschließen.

### Wie das Zeitzonen-Handling funktioniert:

1. **Automatische Browser-Erkennung (Urlaubsmodus):**
   Sobald du die Web-App aufrufst, liest ein JavaScript deine lokale Zeitzone des Browsers aus und speichert sie im Cookie `django_timezone` (z. B. `Europe/Athens`, wenn du in Griechenland bist). Alle Termine, die du auf der Webseite siehst oder einträgst, werden vollautomatisch und **ohne Umrechnung** in dieser Zeitzone angezeigt und verarbeitet.
2. **Heimat-Zeitzone (In den Einstellungen):**
   In deinen **⚙️ Einstellungen** legst du eine feste **Heimat-Zeitzone** fest (z. B. `Europe/Berlin`). Wenn du im Urlaub bist, kannst du auf das schicke **Standort-Pin-Symbol (📍)** klicken, um deine aktuelle Urlaubs-Zeitzone automatisch zu ermitteln, auszuwählen und abzuspeichern.
3. **Der iCal Outlook-Verschiebungs-Fix:**
   Frühere Versionen gaben Kalenderzeiten in Weltzeit (UTC, z. B. `15:00:00Z`) aus. **Microsoft Outlook hat hierbei einen bekannten Fehler:** Bei abonnierten Feeds unterschlägt Outlook oft den Sommer-/Winterzeit-Wechsel (DST) und verschiebt deine Termine um 1 bis 2 Stunden.
   **Die Buckezz-Lösung:** Alle Termine im iCal-Export werden jetzt in deiner lokalen Heimat-Uhrzeit, kombiniert mit dem expliziten Zeitzonen-Parameter (`TZID`), exportiert:
   ```ical
   DTSTART;TZID=Europe/Berlin:20260520T170000
   ```
   Outlook übernimmt diese Zeit dadurch **zu 100 % exakt und unberührt**, wodurch keinerlei Verschiebungen mehr entstehen!

---

## 🎙️ Smart Alexa Integration (Schritt-für-Schritt)

Du kannst Buckezz ganz einfach an deinen **Amazon Alexa Account** anbinden, um Einträge (z. B. auf deine Einkaufsliste) direkt per Sprache zu diktieren. 

Unser integrierter deutscher NLP-Parser versteht komplexe Sätze wie:
> *"Alexa, sag Buckezz setze drei Packungen laktosefreie Milch von Rewe für ein Euro neunundneunzig auf die Liste."*
> **Ergebnis in Buckezz:** Bezeichnung: `laktosefreie Milch` | Menge: `3 Packungen` | Marke: `Rewe` | Preis: `1.99 €`.

### Schritt 1: Deinen persönlichen API-Endpoint finden
Jede deiner Listen in Buckezz hat eine eindeutige ID. Deine persönliche API-Schnittstelle lautet:
`https://deine.domain.de/api/alexa/<listen-uuid-token>/`
*Den genauen Link findest du direkt im Reiter **Teilen / API** deiner jeweiligen Liste in Buckezz.*

### Schritt 2: Custom Skill in der Amazon Developer Console anlegen
1. Melde dich auf der [Amazon Developer Console](https://developer.amazon.com/) an.
2. Klicke auf **Create Skill** (Skill erstellen).
3. **Skill Name:** `Buckezz` (oder ein beliebiger Name deiner Wahl).
4. **Primary Language:** `German` (Deutsch).
5. **Choose a model to add to your skill:** `Custom` (Benutzerdefiniert).
6. **Choose a method to host your skill's backend resources:** `Provision your own` (Eigenes Backend bereitstellen).
7. Klicke oben rechts auf **Create Skill**.

### Schritt 3: Den Endpunkt (Endpoint) hinterlegen
1. Klicke im linken Menü des Skills auf **Endpoint**.
2. Wähle **HTTPS** als Service Endpoint Type aus.
3. Trage im Feld **Default Region** deine persönliche Schnittstellen-URL ein (z. B. `https://deine.domain.de/api/alexa/ad6d142e-8c03-4c68-8c18-b1d9c380c93a/`).
4. Wähle im Dropdown-Menü darunter den SSL-Zertifikatstyp aus: 
   * *„My development endpoint is a sub-domain of a domain that has a wildcard certificate from a certificate authority“* (für Standard-SSL-Zertifikate wie Let's Encrypt).
5. Klicke oben auf **Save Endpoints**.

### Schritt 4: Das Interaktionsmodell (Interaction Model) einspielen
1. Klicke im linken Menü auf **Interaction Model** > **JSON Editor**.
2. Lösche den gesamten Inhalt des Textfeldes und füge das folgende vollständige JSON-Schema ein:

```json
{
  "interactionModel": {
    "languageModel": {
      "invocationName": "buckezz",
      "intents": [
        {
          "name": "AddItemIntent",
          "slots": [
            {
              "name": "item",
              "type": "AMAZON.SearchQuery"
            }
          ],
          "samples": [
            "setze {item} auf die einkaufsliste",
            "packe {item} auf die einkaufsliste",
            "schreibe {item} auf die einkaufsliste",
            "setze {item} auf die liste",
            "packe {item} auf die liste",
            "schreibe {item} auf die liste",
            "füge {item} hinzu",
            "setze {item}",
            "packe {item}"
          ]
        },
        {
          "name": "AMAZON.CancelIntent",
          "samples": []
        },
        {
          "name": "AMAZON.HelpIntent",
          "samples": []
        },
        {
          "name": "AMAZON.StopIntent",
          "samples": []
        },
        {
          "name": "AMAZON.NavigateHomeIntent",
          "samples": []
        },
        {
          "name": "AMAZON.FallbackIntent",
          "samples": []
        }
      ],
      "types": []
    }
  }
}
```

3. Klicke oben auf **Save Model** (Modell speichern).
4. Klicke auf **Build Model** (Modell erstellen). Nach ca. 1-2 Minuten ist das Interaktionsmodell fertig generiert.

### Schritt 5: Testen!
Du kannst den Skill jetzt direkt in der Konsole im Reiter **Test** (oben) oder auf all deinen verknüpften Alexa-Geräten zu Hause aktivieren und testen!
*   *„Alexa, öffne Buckezz!“* -> Antwort: *„Hallo! Welches Element möchtest du auf die Einkaufsliste setzen?“*
*   *„Alexa, sag Buckezz setze Mehl auf die Liste!“* -> Antwort: *„Ich habe Mehl auf deine Liste Einkaufsliste gesetzt.“*
*   *„Alexa, sag Buckezz setze 4 Flaschen trockenen Rotwein von Aldi für 3,99 Euro auf die Liste!“* -> Antwort: *„Ich habe 4 Flaschen trockenen Rotwein von Aldi für 3,99 Euro auf deine Liste Weinvorrat gesetzt.“*

### 👥 Haushalts-Sprachsteuerung & Alexa-Multi-User-Routing (Premium)
Buckezz unterstützt echtes **Multi-User Voice Routing** für den gesamten Haushalt! Wenn verschiedene Personen mit Alexa sprechen, kann Buckezz die Stimmen unterscheiden und die Einträge automatisch auf die persönlichen oder geteilten Listen (Shared Lists) der jeweiligen Person routen:

1. **Alexa-ID hinterlegen:** Jedes Haushaltsmitglied hinterlegt in seinen persönlichen **⚙️ Einstellungen** seine eindeutige Alexa-User-ID (wird im Alexa-Entwickler-Protokoll oder Debug-Log angezeigt).
2. **Kollaboratives Routing:** Fügt eine Person (z. B. dein Partner oder dein Kind) per Sprache einen Eintrag hinzu, ermittelt der NLP-Parser den Sprecher und sucht nach passenden Listen, die entweder dem Sprecher gehören oder mit ihm **geteilt (shared)** sind.
3. **Schlüsselwort-Kategorisierung:** Das System ordnet Aufgaben anhand von Schlüsselwörtern wie *"to do"*, *"hausarbeit"*, *"einkauf"* o.ä. vollautomatisch der richtigen Liste zu und filtert das Trigger-Wort aus dem Titel, um die Listen sauber zu halten.

---

## 🎨 Design Studio & Farbthemen

Buckezz 2.0 nutzt **Django Design Studio** für ein einheitliches Erscheinungsbild im gesamten Frontend und Admin-Bereich.

* **Visuelle Anpassung:** Über den Menüpunkt **Design Studio** in den Einstellungen passt du Primär-/Akzentfarben, Hell-/Dunkelmodus, Layout-Dichte, Schriftarten und Hintergründe in Echtzeit an.
* **Design-Icons & Emojis:** Im Vorlagen-Studio lassen sich für Kategorien und Buckets sowohl einfärbbare Bootstrap-Icons (`bi-*` passend zur Theme-Farbe) als auch bunte Emojis auswählen.

---

## 🔄 Wartung, Updates & PWA-Cache

### App aktualisieren
Wenn ein neues Update bereitsteht, kannst du die Anwendung auf deinem Server/NAS ganz einfach aktualisieren (alle Baukasten-Kits liegen persistent im Volume `ds_pkg:/opt/ds-pkg`, Mandanten werden automatisch über `migrate_all` migriert):

```bash
# Schnelles Update (Git Pull + geänderte Kits nach /opt/ds-pkg + migrate_all + Restart)
./docker/update-fast.sh

# Vollständiger Container-Rebuild (inkl. /opt/ds-pkg-Sync)
./docker/update.sh
```

### PWA-Cache auf dem Handy/Browser leeren
Da Progressive Web Apps (PWA) Assets extrem hartnäckig cachen, siehst du Updates auf deinem Handy oft erst verzögert.
* Geh dazu einfach in Buckezz in deine **⚙️ Einstellungen**.
* Scrolle ganz nach unten zum Bereich **📱 App-Cache & PWA**.
* Klicke auf **"🔄 App-Cache leeren & aktualisieren"**. 
* Deine App deregistriert sofort alle Service Worker, löscht den Cache und lädt sich in unter einer Sekunde brandneu vom Server herunter.
