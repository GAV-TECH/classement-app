from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from datetime import datetime
DB_PATH = "/home/GAVTECH/classement_app/database.db"
app = Flask(__name__)
DATABASE = "database.db"


# =====================
# DATABASE
# =====================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            group_name TEXT NOT NULL,
            display_order INTEGER NOT NULL,
            UNIQUE(name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            game_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            value INTEGER NOT NULL,
            UNIQUE(player_id, game_id, date),
            FOREIGN KEY (player_id) REFERENCES players (id),
            FOREIGN KEY (game_id) REFERENCES games (id)
        )
    """)

    games = [
        ("SUTOM", "SUTOM", 1),
        ("Le Mot – 4 lettres", "LE_MOT", 1),
        ("Le Mot – 5 lettres", "LE_MOT", 2),
        ("Le Mot – 6 lettres", "LE_MOT", 3),
        ("Wordle – Anglais", "WORDLE", 1),
        ("Wordle – Français", "WORDLE", 2),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO games (name, group_name, display_order)
        VALUES (?, ?, ?)
    """, games)

    conn.commit()
    conn.close()


# =====================
# PAGES
# =====================
@app.route("/")
def index():
    conn = sqlite3.connect(DB_PATH)


    players = conn.execute(
        "SELECT id, name FROM players ORDER BY name"
    ).fetchall()

    games = conn.execute("""
        SELECT * FROM games
        ORDER BY
            CASE group_name
                WHEN 'SUTOM' THEN 1
                WHEN 'LE_MOT' THEN 2
                WHEN 'WORDLE' THEN 3
            END,
            display_order
    """).fetchall()

    total_games = len(games)
    players_status = []

    for player in players:
        played_today = conn.execute("""
            SELECT COUNT(DISTINCT game_id)
            FROM scores
            WHERE player_id = ?
              AND date = DATE('now', 'localtime')
        """, (player["id"],)).fetchone()[0]

        players_status.append({
            "id": player["id"],
            "name": player["name"],
            "done": played_today == total_games
        })

    conn.close()

    show_reveal_week = datetime.today().weekday() == 0  # lundi

    return render_template(
        "index.html",
        players=players,
        players_status=players_status,
        games=games,
        show_reveal_week=show_reveal_week
    )


@app.route("/create", methods=["GET", "POST"])
def create_player():
    if request.method == "POST":
        conn = get_db()
        conn.execute(
            "INSERT INTO players (name, code) VALUES (?, ?)",
            (request.form["name"], request.form["code"])
        )
        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    return render_template("create.html")


@app.route("/login/<int:player_id>", methods=["GET", "POST"])
def login(player_id):
    conn = get_db()

    player = conn.execute(
        "SELECT * FROM players WHERE id = ?",
        (player_id,)
    ).fetchone()

    if not player:
        conn.close()
        return "Joueur introuvable", 404

    error = None

    # Nombre total de jeux (pour le verrouillage)
    total_games = conn.execute(
        "SELECT COUNT(*) FROM games"
    ).fetchone()[0]

    if request.method == "POST":
        if request.form["code"] == player["code"]:

            games = conn.execute("""
                SELECT * FROM games
                ORDER BY
                    CASE group_name
                        WHEN 'SUTOM' THEN 1
                        WHEN 'LE_MOT' THEN 2
                        WHEN 'WORDLE' THEN 3
                    END,
                    display_order
            """).fetchall()

            scores = conn.execute("""
                SELECT game_id, value
                FROM scores
                WHERE player_id = ?
                  AND date = DATE('now', 'localtime')
            """, (player_id,)).fetchall()

            scores_dict = {s["game_id"]: s["value"] for s in scores}

            # ✅ CORRECTION IMPORTANTE
            # Le joueur est verrouillé SEULEMENT s’il a joué TOUS les jeux
            locked = len(scores_dict) == total_games

            conn.close()

            return render_template(
                "player.html",
                player=player,
                games=games,
                scores=scores_dict,
                locked=locked
            )
        else:
            error = "Code incorrect ❌"

    conn.close()
    return render_template("login.html", player=player, error=error)

# =====================
# SCORES
# =====================
@app.route("/save_scores/<int:player_id>", methods=["POST"])
def save_scores(player_id):
    conn = get_db()
    games = conn.execute("SELECT id FROM games").fetchall()

    for game in games:
        value = request.form.get(f"game_{game['id']}")
        if value and value.isdigit():
            value = int(value)
            if 1 <= value <= 7:
                conn.execute("""
                    INSERT INTO scores (player_id, game_id, date, value)
                    VALUES (?, ?, DATE('now', 'localtime'), ?)
                    ON CONFLICT(player_id, game_id, date)
                    DO UPDATE SET value = excluded.value
                """, (player_id, game["id"], value))

    conn.commit()
    conn.close()
    return redirect(url_for("login", player_id=player_id))


@app.route("/edit/<int:player_id>")
def edit_scores(player_id):
    conn = get_db()
    player = conn.execute(
        "SELECT * FROM players WHERE id = ?",
        (player_id,)
    ).fetchone()

    games = conn.execute("""
        SELECT * FROM games
        ORDER BY
            CASE group_name
                WHEN 'SUTOM' THEN 1
                WHEN 'LE_MOT' THEN 2
                WHEN 'WORDLE' THEN 3
            END,
            display_order
    """).fetchall()

    scores = conn.execute("""
        SELECT game_id, value
        FROM scores
        WHERE player_id = ?
          AND date = DATE('now', 'localtime')
    """, (player_id,)).fetchall()

    conn.close()

    return render_template(
        "player.html",
        player=player,
        games=games,
        scores={s["game_id"]: s["value"] for s in scores},
        locked=False
    )


# =====================
# AJAX – SCORES PAR JEU
# =====================
@app.route("/scores/<int:game_id>/<int:player_id>")
def game_scores(game_id, player_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT p.name, s.value
        FROM players p
        LEFT JOIN scores s
            ON p.id = s.player_id
            AND s.game_id = ?
            AND s.date = DATE('now', 'localtime')
        ORDER BY p.name
    """, (game_id,)).fetchall()
    conn.close()

    return jsonify([
        {"name": r["name"], "value": r["value"]}
        for r in rows
    ])


# =====================
# LEADERBOARDS – JOUR
# =====================
@app.route("/leaderboard/day/global")
def leaderboard_day_global():
    conn = get_db()
    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

    rows = conn.execute("""
        SELECT p.name, SUM(s.value) AS total
        FROM scores s
        JOIN players p ON p.id = s.player_id
        WHERE s.date = DATE('now', 'localtime')
        GROUP BY p.id
        HAVING COUNT(s.id) = ?
        ORDER BY total ASC
    """, (total_games,)).fetchall()

    conn.close()

    return jsonify([
        {"rank": i + 1, "name": r["name"], "score": r["total"]}
        for i, r in enumerate(rows)
    ])


@app.route("/leaderboard/day/game/<int:game_id>")
def leaderboard_day_game(game_id):
    conn = get_db()

    rows = conn.execute("""
        SELECT p.name, s.value
        FROM players p
        LEFT JOIN scores s
            ON p.id = s.player_id
            AND s.game_id = ?
            AND s.date = DATE('now', 'localtime')
        ORDER BY
            CASE WHEN s.value IS NULL THEN 1 ELSE 0 END,
            s.value ASC
    """, (game_id,)).fetchall()

    conn.close()

    return jsonify([
        {"rank": i + 1, "name": r["name"], "score": r["value"]}
        for i, r in enumerate(rows)
    ])


@app.route("/leaderboard/yesterday/global")
def leaderboard_yesterday_global():
    conn = get_db()
    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

    rows = conn.execute("""
        SELECT p.name, SUM(s.value) AS total
        FROM scores s
        JOIN players p ON p.id = s.player_id
        WHERE s.date = DATE('now', 'localtime', '-1 day')
        GROUP BY p.id
        HAVING COUNT(DISTINCT s.game_id) = ?
        ORDER BY total ASC
    """, (total_games,)).fetchall()

    conn.close()

    return jsonify([
        {"rank": i + 1, "name": r["name"], "score": r["total"]}
        for i, r in enumerate(rows)
    ])


@app.route("/leaderboard/week/global")
def leaderboard_week_global():
    conn = get_db()
    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

    rows = conn.execute("""
        SELECT p.name, SUM(s.value) AS total
        FROM scores s
        JOIN players p ON p.id = s.player_id
        WHERE s.date >= DATE('now', 'localtime', '-6 days', 'weekday 1')
        GROUP BY p.id
        HAVING COUNT(DISTINCT s.game_id) = ?
        ORDER BY total ASC
    """, (total_games,)).fetchall()

    conn.close()

    return jsonify([
        {"rank": i + 1, "name": r["name"], "score": r["total"]}
        for i, r in enumerate(rows)
    ])


# =====================
# REVEAL
# =====================
@app.route("/reveal")
def reveal():
    return render_template("reveal.html")


@app.route("/reveal/week")
def reveal_week():
    return render_template("reveal_week.html")


# =====================
# DELETE PLAYER
# =====================
@app.route("/delete_player/<int:player_id>", methods=["POST"])
def delete_player(player_id):
    conn = get_db()

    player = conn.execute(
        "SELECT code FROM players WHERE id = ?",
        (player_id,)
    ).fetchone()

    if not player:
        conn.close()
        return "Joueur introuvable", 404

    entered_code = request.form.get("code")

    # ❌ Mauvais code → refus
    if entered_code != player["code"]:
        conn.close()
        return "Code incorrect ❌ Suppression refusée", 403

    # ✅ Bon code → suppression
    conn.execute("DELETE FROM scores WHERE player_id = ?", (player_id,))
    conn.execute("DELETE FROM players WHERE id = ?", (player_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("index"))


@app.route("/stats/player/<int:player_id>")
def stats_player(player_id):
    conn = get_db()

    total_games = conn.execute(
        "SELECT COUNT(*) FROM games"
    ).fetchone()[0]

    # 🔒 Journées COMPLÈTES uniquement
    rows = conn.execute("""
        SELECT
            s.date,
            s.player_id,
            SUM(s.value) AS total
        FROM scores s
        GROUP BY s.date, s.player_id
        HAVING COUNT(DISTINCT s.game_id) = ?
    """, (total_games,)).fetchall()

    conn.close()

    # 🚫 Aucun score → aucune stat
    if not rows:
        return jsonify({
            "podium_day": {"first": 0, "second": 0, "third": 0},
            "podium_week": {"first": 0, "second": 0, "third": 0}
        })

    from collections import defaultdict
    from datetime import datetime, timedelta

    rankings_by_date = defaultdict(list)
    for r in rows:
        rankings_by_date[r["date"]].append(r)

    # 🚫 Le joueur n’apparaît jamais → aucune stat
    if not any(r["player_id"] == player_id for r in rows):
        return jsonify({
            "podium_day": {"first": 0, "second": 0, "third": 0},
            "podium_week": {"first": 0, "second": 0, "third": 0}
        })

    podium_day = {"first": 0, "second": 0, "third": 0}
    podium_week = {"first": 0, "second": 0, "third": 0}

    today = datetime.today().date()
    week_start = today - timedelta(days=today.weekday())

    # 🔒 UN SEUL PODIUM PAR JOUR
    for date_str, ranking in rankings_by_date.items():

        if len(ranking) < 2:
            continue  # pas de classement valable

        # 🔥 CORRECTION CRITIQUE : tri par score
        ranking.sort(key=lambda x: x["total"])

        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        top3 = ranking[:3]

        for idx, r in enumerate(top3):
            if r["player_id"] != player_id:
                continue

            if idx == 0:
                podium_day["first"] += 1
                if date >= week_start:
                    podium_week["first"] += 1
            elif idx == 1:
                podium_day["second"] += 1
                if date >= week_start:
                    podium_week["second"] += 1
            elif idx == 2:
                podium_day["third"] += 1
                if date >= week_start:
                    podium_week["third"] += 1

    return jsonify({
        "podium_day": podium_day,
        "podium_week": podium_week
    })

@app.route("/stats/game/<int:game_id>")
def stats_game(game_id):
    conn = get_db()

    total_games = conn.execute(
        "SELECT COUNT(*) FROM games"
    ).fetchone()[0]

    game = conn.execute(
        "SELECT name FROM games WHERE id = ?",
        (game_id,)
    ).fetchone()

    if not game:
        conn.close()
        return jsonify({"error": "Jeu introuvable"}), 404

    # 🔒 Score moyen UNIQUEMENT sur journées complètes
    avg_score = conn.execute("""
        SELECT AVG(s.value)
        FROM scores s
        WHERE s.game_id = ?
          AND EXISTS (
              SELECT 1
              FROM scores s2
              WHERE s2.date = s.date
                AND s2.player_id = s.player_id
              GROUP BY s2.date, s2.player_id
              HAVING COUNT(DISTINCT s2.game_id) = ?
          )
    """, (game_id, total_games)).fetchone()[0]

    # 🔒 Meilleur joueur (moyenne la plus basse, journées complètes)
    best_player = conn.execute("""
        SELECT p.name, AVG(s.value) AS avg_score
        FROM scores s
        JOIN players p ON p.id = s.player_id
        WHERE s.game_id = ?
          AND EXISTS (
              SELECT 1
              FROM scores s2
              WHERE s2.date = s.date
                AND s2.player_id = s.player_id
              GROUP BY s2.date, s2.player_id
              HAVING COUNT(DISTINCT s2.game_id) = ?
          )
        GROUP BY p.id
        ORDER BY avg_score ASC
        LIMIT 1
    """, (game_id, total_games)).fetchone()

    conn.close()

    return jsonify({
        "game": game["name"],
        "avg_score": round(avg_score, 2) if avg_score is not None else None,
        "best_player": best_player["name"] if best_player else None
    })

@app.route("/stats/chart/avg-global")
def stats_chart_avg_global():
    conn = get_db()

    rows = conn.execute("""
        SELECT
            p.name AS player,
            SUM(s.value) * 1.0 / COUNT(s.id) AS avg_attempts
        FROM scores s
        JOIN players p ON p.id = s.player_id
        GROUP BY p.id
        HAVING COUNT(s.id) > 0
        ORDER BY avg_attempts ASC
    """).fetchall()

    conn.close()

    return jsonify([
        {
            "player": r["player"],
            "avg": round(r["avg_attempts"], 2)
        }
        for r in rows
    ])

@app.route("/debug/days")
def debug_days():
    conn = get_db()
    rows = conn.execute("""
        SELECT date, player_id, COUNT(DISTINCT game_id) AS c
        FROM scores
        GROUP BY date, player_id
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])




# =====================
# START
# =====================
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

