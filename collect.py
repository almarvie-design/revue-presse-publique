#!/usr/bin/env python3
"""Collecte quotidienne des flux RSS/Atom de la revue de presse.
Écrit data/latest.json (articles des JOURS derniers jours : média, titre, lien, date, résumé).
Uniquement bibliothèque standard. Les flux en échec sont listés dans 'errors'."""
import json, sys, re, html, datetime as dt, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
JOURS = 4
JOURS_TEXTE = 2          # texte intégral récupéré pour les articles des 2 derniers jours
MAX_TEXTES = 500
TEXTE_MAX = 9000         # caractères conservés par article
# Médias payants ou à paywall : titre + chapô seulement (jamais le corps de l'article)
PAYANTS = {"Le Monde","Libération","Mediapart","Le Canard enchaîné","Contexte","Le Monde diplomatique",
  "Alternatives Économiques","Arrêt sur images","Le 1","Esprit","Les Jours","AOC","Le Grand Continent",
  "Mediacités","Socialter","XXI","Next","La Croix","Courrier international","Politis","L'Humanité",
  "Rue89 Bordeaux","Fakir","Le Média","La Vie des idées","Frustration","Ballast","Le Comptoir"}
UA = "Mozilla/5.0 (compatible; revue-de-presse-bot/1.0; veille personnelle)"
now = dt.datetime.now(dt.timezone.utc)
since = now - dt.timedelta(days=JOURS)

def parse_date(s):
    if not s: return None
    s = s.strip()
    from email.utils import parsedate_to_datetime
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
    return d

def clean(t, n=500):
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    return re.sub(r"\s+", " ", t).strip()[:n]

def local(tag): return tag.rsplit("}", 1)[-1]

def fetch(item):
    src, url = item
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"})
        raw = urllib.request.urlopen(req, timeout=30).read()
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            # flux mal formé : on retire les caractères de contrôle et on réessaie
            txt = raw.decode("utf-8", "ignore")
            txt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", txt)
            txt = re.sub(r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", txt)
            root = ET.fromstring(txt.encode("utf-8"))
    except Exception as e:
        return src, url, [], f"{type(e).__name__}: {e}"
    out = []
    for it in root.iter():
        if local(it.tag) not in ("item", "entry"): continue
        f = {local(c.tag): c for c in it}
        title = clean(f["title"].text if "title" in f else "", 300)
        link = ""
        if "link" in f:
            link = f["link"].get("href") or (f["link"].text or "")
        date = None
        for k in ("pubDate", "published", "updated", "date"):
            if k in f and f[k].text:
                date = parse_date(f[k].text); break
        summ = ""
        for k in ("description", "summary", "encoded", "content"):
            if k in f and f[k].text:
                summ = clean(f[k].text); break
        if title and link and (date is None or date >= since):
            rec = {"src": src, "titre": title, "url": link.strip(), "date": date.isoformat() if date else None, "resume": summ}
            if src.startswith("mot:") and "source" in f and f["source"].text:
                rec["src"] = clean(f["source"].text, 80); rec["mot"] = src[4:]
            out.append(rec)
    if src.startswith("mot:"): out = out[:30]
    return src, url, out, None

def texte(a):
    """Corps de l'article via trafilatura ; si trop court, on le considère payant (titre + chapô seulement)."""
    try:
        import trafilatura
        req = urllib.request.Request(a["url"], headers={"User-Agent": UA})
        h = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        t = trafilatura.extract(h, include_comments=False, include_tables=False) or ""
    except Exception as e:
        a["texte_erreur"] = f"{type(e).__name__}"; return a
    if len(t) < 700:
        a["pay"] = True          # corps absent ou tronqué : probable paywall
    else:
        a["texte"] = t[:TEXTE_MAX]
    return a

def decode_gnews(url, timeout=15):
    """Lien Google Actualités -> URL directe de l'article (None si échec : on garde alors le lien d'origine)."""
    m=re.search(r"/articles/([^?/]+)",url)
    if not m: return None
    gid=m.group(1)
    for base in ("https://news.google.com/articles/","https://news.google.com/rss/articles/"):
        try:
            h=urllib.request.urlopen(urllib.request.Request(base+gid,headers={"User-Agent":UA}),timeout=timeout).read().decode("utf-8","ignore")
            sg=re.search(r'data-n-a-sg="([^"]+)"',h); ts=re.search(r'data-n-a-ts="([^"]+)"',h)
            if sg and ts: break
        except Exception: pass
    else: return None
    inner=json.dumps(["garturlreq",[["X","X",["X","X"],None,None,1,1,"FR:fr",None,1,None,None,None,None,None,0,1],"X","X",1,[1,1,1],1,1,None,0,0,None,0],gid,int(ts.group(1)),sg.group(1)],separators=(",",":"))
    body="f.req="+urllib.parse.quote(json.dumps([[["Fbv4je",inner,None,"generic"]]],separators=(",",":")))
    req=urllib.request.Request("https://news.google.com/_/DotsSplashUi/data/batchexecute",data=body.encode(),headers={"User-Agent":UA,"Content-Type":"application/x-www-form-urlencoded;charset=UTF-8"})
    try:
        t=urllib.request.urlopen(req,timeout=timeout).read().decode("utf-8","ignore")
        return json.loads(json.loads(t.split("\n\n",1)[1])[0][2])[1]
    except Exception: return None

import unicodedata
def _norm(t): return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode())
def retire_suffixe_media(a):
    """Titres Google Actualités « Titre - Nom du site » : retire le nom du site si c'est bien le média de l'article."""
    if " - " not in a["titre"]: return
    tete, suf = a["titre"].rsplit(" - ", 1)
    n, m = _norm(suf), _norm(a["src"])
    if tete.strip() and n and (n == m or n in m or m in n or re.search(r"\.(fr|com|org|net|info)$", suf.strip().lower())):
        a["titre"] = tete.strip()

def main():
    items = []
    for l in open("feeds.txt", encoding="utf-8"):
        if "|" in l and not l.startswith("#"):
            a, u = l.strip().split("|", 1); items.append((a, u))
    for l in open("gnews_sites.txt", encoding="utf-8"):
        if "|" in l:
            a, d = l.strip().split("|", 1)
            q = urllib.parse.quote(f"site:{d} when:{JOURS}d")
            items.append((a, f"https://news.google.com/rss/search?q={q}&hl=fr&gl=FR&ceid=FR:fr"))
    try:
        for l in open("gnews_mots.txt", encoding="utf-8"):
            l = l.strip()
            if l and not l.startswith("#"):
                q = urllib.parse.quote(f"{l} when:2d")
                items.append(("mot:" + l, f"https://news.google.com/rss/search?q={q}&hl=fr&gl=FR&ceid=FR:fr"))
    except FileNotFoundError:
        pass
    noms = {re.sub(r"[^a-z0-9]", "", a.lower()) for a, _ in items if not a.startswith("mot:")}
    arts, errors, seen = [], [], set()
    with ThreadPoolExecutor(max_workers=12) as ex:
        for src, url, out, err in ex.map(fetch, items):
            if err: errors.append({"src": src, "feed": url, "erreur": err})
            for a in out:
                if a["url"] in seen: continue
                seen.add(a["url"]); arts.append(a)
    for a in arts:
        if "mot" in a:
            n = re.sub(r"[^a-z0-9]", "", a["src"].lower())
            a["ht"] = not any(n == x or (len(x) > 4 and (x in n or n in x)) for x in noms)
    # Liens Google Actualités -> liens directs (repli : lien d'origine conservé dans 'url_gnews')
    gn = [a for a in arts if "news.google.com/rss/articles/" in a["url"]]
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda a: decode_gnews(a["url"]), gn))
    ok, deja = 0, {a["url"] for a in arts}
    for a, r in zip(gn, res):
        if r and r.startswith("http"):
            a["url_gnews"] = a["url"]; a["url"] = r; ok += 1
    print(f"liens Google Actualités décodés : {ok}/{len(gn)}")
    for a in arts:
        if "url_gnews" in a or "news.google.com" in a["url"]: retire_suffixe_media(a)
    vus, uniq = set(), []
    for a in arts:
        if a["url"] in vus: continue
        vus.add(a["url"]); uniq.append(a)
    arts = uniq
    arts.sort(key=lambda a: a["date"] or "", reverse=True)
    lim = (now - dt.timedelta(days=JOURS_TEXTE)).isoformat()
    cand = []
    for a in arts:
        a["pay"] = a["src"] in PAYANTS
        if not a["pay"] and (a["date"] or "9") >= lim and len(cand) < MAX_TEXTES and "news.google.com" not in a["url"] and "url_gnews" not in a:
            cand.append(a)
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(texte, cand))
    # Dépôt public : on ne publie jamais le texte intégral (droit d'auteur), seulement titre, lien, date, chapô.
    for a in arts:
        a.pop("texte", None); a.pop("texte_erreur", None)
    json.dump({"genere": now.isoformat(), "jours": JOURS, "nb_articles": len(arts), "nb_flux": len(items), "nb_erreurs": len(errors), "articles": arts, "errors": errors},
              open("data/latest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(arts)} articles, {len(errors)} flux en erreur sur {len(items)}")
if __name__ == "__main__": main()
