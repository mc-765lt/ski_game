"""第11回配布教材：ASCIIスキーゲーム（学生版）。

実行：python w11_ski_demo.py
Windowsで curses が見つからない場合：py -m pip install windows-curses

w11演習01：update_distance_score() の中だけを実装する。
"""

import os
import random
import sqlite3
import time
from collections import deque
from contextlib import closing
from pathlib import Path

try:
    import curses
except ImportError:
    raise SystemExit(
        "curses を読み込めません。Windowsでは "
        "'py -m pip install windows-curses' を実行してください。"
    )


# 画面とゲームの基本設定
FPS = 30
MIN_COLUMNS = 64
MIN_LINES = 21
MAX_FIELD_WIDTH = 68
MIN_COURSE_HALF_WIDTH = 8
NARROW_PER_LEVEL = 1
FIELD_TOP = 4
FOOTER_HEIGHT = 5  # 凡例2行、状態、操作説明、最下行の余白
STATUS_READY = "READY"
STATUS_PLAYING = "PLAYING"
STATUS_PAUSED = "PAUSED"
STATUS_GAME_OVER = "GAME_OVER"

# アイテム・ライフ・雪玉の設定（時間の単位は秒）
MAX_LIVES = 3
SLOW_DURATION = 5.0
SLOW_FACTOR = 0.5
MAGNET_DURATION = 8.0
MAGNET_RADIUS = 4  # 縦横の距離の合計が4マス以内
INVINCIBLE_DURATION = 1.5
SHAKE_DURATION = 0.35
SNOWBALL_SPEED = 5.0  # 1秒間に横へ進むマス数
SNOWBALL_RATE = 0.12
ITEM_RATE = 0.08
PICKUP_HALF_WIDTH = 1  # アイテムとコインは同じ行の左右1マスまで取得可能
SECTION_ROWS = 40
COIN_TRAIL_START = 4  # 各区間の5行目から
COIN_TRAIL_LENGTH = 4
DATA_DIR = Path(os.getenv("LOCALAPPDATA") or os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
RECORDS_PATH = DATA_DIR / "w11_SkiGame" / "records.sqlite3"


def clamp(value, minimum, maximum):
    """値が指定範囲からはみ出さないようにする。"""
    return max(minimum, min(value, maximum))


def create_state(field_width, field_height, rng, difficulty="normal"):
    """新しいゲームを開始するためのStateを用意する。"""
    half_width = min(19, max(13, (field_width - 12) // 2))
    state = {
        "status": STATUS_READY,
        "difficulty": difficulty,
        "x": field_width // 2,
        "y": max(3, int(field_height * 0.35)),
        "direction": 1,     # -1: 左、+1: 右。直進（0）は使わない。
        "speed": 1.0,
        "base_speed": 1.5,
        "elapsed_time": 0.0,   # 一時停止中は増えない
        "scroll_count": 0,    # コースが進んだ行数
        "score": 0,           # w11演習01で更新する
        "coins_collected": 0,
        "coin_trail": deque(),
        "personal_bests": None,
        "level": 1,           # 100行進むごとに上昇
        "scroll_progress": 0.0,
        "field_width": field_width,
        "field_height": field_height,
        "course_center": field_width // 2,
        "course_half_width": half_width,
        "initial_half_width": half_width,
        "rows": deque(),
        "game_over_reason": "",
        "lives": MAX_LIVES,
        "slow_timer": 0.0,
        "magnet_timer": 0.0,
        "invincible_timer": 0.0,
        "shake_timer": 0.0,
    }

    # 開始直後の画面には障害物や取得物を置かない。
    for _ in range(field_height):
        state["rows"].append(create_course_row(state, rng, with_tree=False))
    return state


def create_course_row(state, rng, with_tree=True):
    """新しい1行にコースの境界、障害物、取得物を配置する。"""
    width = state["field_width"]
    half = state["course_half_width"]
    target_half = max(MIN_COURSE_HALF_WIDTH, state["initial_half_width"] - (state["level"] - 1) * NARROW_PER_LEVEL)
    half = min(half, target_half)  # レベルごとの目標幅を上限に、幅をランダムに変化させる。

    # 崖の幅とコース中心を急激に変化させず、通れる幅を確保する。
    if rng.random() < 0.13:
        half = int(clamp(half + rng.choice([-1, 1]), MIN_COURSE_HALF_WIDTH, target_half))
    center = state["course_center"] + rng.choice([-1, 0, 0, 0, 0, 1])
    center = int(clamp(center, half + 3, width - half - 4))
    state["course_center"] = center
    state["course_half_width"] = half

    left = center - half
    right = center + half
    if not with_tree:
        return {"left": left, "right": right, "tree": None, "coin": None,
                "snowball": None, "item": None}

    # 縦または斜めの4枚を、1行につき1枚ずつ画面に送り込む。
    if state["scroll_count"] % SECTION_ROWS == COIN_TRAIL_START:
        step = rng.choice((-1, 0, 1))
        start = center + rng.randint(-1, 1) - step * (COIN_TRAIL_LENGTH // 2)
        state["coin_trail"].extend(start + i * step for i in range(COIN_TRAIL_LENGTH))
    coin = state["coin_trail"].popleft() if state["coin_trail"] else None
    available = [x for x in range(left + 3, right - 2) if x != coin]

    tree = None
    tree_rate = min(0.52, 0.23 + (state["level"] - 1) * 0.055)
    if state["difficulty"] == "hard":
        tree_rate = tree_rate * 1.5
    if rng.random() < tree_rate:
        tree_spaces = [x for x in available if coin is None or abs(x - coin) > PICKUP_HALF_WIDTH]
        tree = rng.choice(tree_spaces)
        available.remove(tree)
    snowball = None
    if coin is None and available and rng.random() < SNOWBALL_RATE:
        snow_x = rng.choice(available)
        available.remove(snow_x)
        snowball = {"x": float(snow_x), "direction": rng.choice([-1, 1])}

    item = None
    if available and rng.random() < ITEM_RATE:
        item = {"x": rng.choice(available), "kind": rng.choice(["S", "M", "+"])}

    return {
        "left": left, "right": right, "tree": tree, "coin": coin,
        "snowball": snowball, "item": item,
    }


def update_distance_score(state):
    """w11演習01：コースが1行進んだときに、1回だけ呼び出される。"""
    if state["scroll_count"] + 1:
        state["score"] += 1  # TODO: Stateの score に1点加算する処理を1行書こう。
    
    
    
    # TODO: Stateの score に1点加算する処理を1行書こう。
    # ヒント：第4章で学んだ辞書の値の更新を利用する。
    pass


def move_course_one_row(state, rng):
    """コースを1行スクロールさせ、距離とレベルを更新する。"""
    # 新しいコースは画面の上に現れ、下（プレイヤー側）へ流れる。
    state["rows"].pop()
    state["rows"].appendleft(create_course_row(state, rng))

    # 直進はできない。1行進むごとに必ず左右どちらかへ1文字移動する。
    state["x"] += state["direction"]
    state["scroll_count"] += 1
    state["level"] = state["scroll_count"] // 100 + 1

    update_distance_score(state)


def take_damage(state, reason):
    """被弾後1.5秒間は追加ダメージを受けない。"""
    if state["status"] != STATUS_PLAYING or state["invincible_timer"] > 0:
        return
    state["lives"] = max(0, state["lives"] - 1)
    state["invincible_timer"] = INVINCIBLE_DURATION
    state["shake_timer"] = SHAKE_DURATION
    if state["lives"] == 0:
        state["game_over_reason"] = reason
        state["status"] = STATUS_GAME_OVER


def collect_item(state, row):
    """左右1マス以内のアイテムを取得。再取得時は効果時間を戻す。"""
    item = row["item"]
    if item is None or abs(item["x"] - int(round(state["x"]))) > PICKUP_HALF_WIDTH:
        return
    if item["kind"] == "S":
        state["slow_timer"] = SLOW_DURATION
    elif item["kind"] == "M":
        state["magnet_timer"] = MAGNET_DURATION
    elif item["kind"] == "+":
        state["lives"] = min(MAX_LIVES, state["lives"] + 1)
    row["item"] = None


def collect_coins(state):
    """通常は同じ行の左右1マスまで回収。磁石使用中は周囲4マス。"""
    player_x = int(round(state["x"]))
    for y, row in enumerate(state["rows"]):
        if row["coin"] is None:
            continue
        dx = abs(row["coin"] - player_x)
        dy = abs(y - state["y"])
        if state["magnet_timer"] > 0:
            in_range = dx + dy <= MAGNET_RADIUS
        else:
            in_range = dy == 0 and dx <= PICKUP_HALF_WIDTH
        if in_range:
            state["score"] += 100
            state["coins_collected"] += 1
            row["coin"] = None


def check_collision(state):
    """崖・木・雪玉への接触とアイテム取得を判定する。"""
    if state["status"] != STATUS_PLAYING:
        return
    player_x = int(round(state["x"]))
    row = state["rows"][state["y"]]
    snowball = row["snowball"]
    if player_x <= row["left"] or player_x >= row["right"]:
        take_damage(state, "CLIFF!")
        # 崖に触れたら内側へ戻し、方向もコース内側へ変える。
        state["x"] = int(clamp(player_x, row["left"] + 1, row["right"] - 1))
        state["direction"] = 1 if player_x <= row["left"] else -1
    elif row["tree"] == player_x:
        take_damage(state, "TREE!")
    elif snowball is not None and int(round(snowball["x"])) == player_x:
        take_damage(state, "SNOWBALL!")

    if state["status"] == STATUS_PLAYING:
        collect_item(state, row)
        collect_coins(state)


def update_snowballs(state, dt, speed_factor):
    """雪玉は横へ移動し、その行の崖の手前で折り返す。"""
    for row in state["rows"]:
        snowball = row["snowball"]
        if snowball is None:
            continue
        snowball["x"] += snowball["direction"] * SNOWBALL_SPEED * speed_factor * dt
        left, right = row["left"] + 1, row["right"] - 1
        if snowball["x"] <= left:
            snowball["x"] = float(left)
            snowball["direction"] = 1
        elif snowball["x"] >= right:
            snowball["x"] = float(right)
            snowball["direction"] = -1


def update_game(state, dt, rng):
    """短い時間刻みで更新し、移動中の雪玉との接触も検出する。"""
    # 最後の被弾による揺れは、ゲームオーバー後も最後まで表示する。
    if state["status"] == STATUS_GAME_OVER:
        state["shake_timer"] = max(0.0, state["shake_timer"] - dt)
        return
    if state["status"] != STATUS_PLAYING:
        return

    remaining = max(0.0, dt)
    while remaining > 0 and state["status"] == STATUS_PLAYING:
        step = min(remaining, 1.0 / 60.0)
        remaining -= step
        state["elapsed_time"] += step
        for name in ("slow_timer", "magnet_timer", "invincible_timer", "shake_timer"):
            state[name] = max(0.0, state[name] - step)

        check_collision(state)
        if state["status"] != STATUS_PLAYING:
            break
        speed_factor = SLOW_FACTOR if state["slow_timer"] > 0 else 1.0
        level_gain = 0.30 if state["difficulty"] == "hard" else 0.15
        normal_speed = min(5.0, state["base_speed"] + (state["level"] - 1) * level_gain)
        state["speed"] = normal_speed * speed_factor

        update_snowballs(state, step, speed_factor)
        check_collision(state)
        if state["status"] != STATUS_PLAYING:
            break
        state["scroll_progress"] += 3.0 * state["speed"] * step
        while state["scroll_progress"] >= 1.0 and state["status"] == STATUS_PLAYING:
            state["scroll_progress"] -= 1.0
            move_course_one_row(state, rng)
            check_collision(state)


def read_key(state, key):
    """キー入力をStateへ反映する。再起動要求なら True を返す。"""
    if key in (ord("q"), ord("Q")):
        return "QUIT"
    if state["status"] == STATUS_READY:
        if key in (ord("n"), ord("N")):
            state["difficulty"] = "normal"
        elif key in (ord("h"), ord("H")):
            state["difficulty"] = "hard"
    if state["status"] == STATUS_GAME_OVER and key in (ord("r"), ord("R")):
        return "RESTART"
    if key == ord(" "):
        if state["status"] in (STATUS_READY, STATUS_PAUSED):
            state["status"] = STATUS_PLAYING
        elif state["status"] == STATUS_PLAYING:
            state["status"] = STATUS_PAUSED
        return None
    if state["status"] == STATUS_PLAYING:
        # 進行方向は左(-1)か右(+1)の二択。
        # 連打しても旋回は強くならない。
        if key == curses.KEY_LEFT:
            state["direction"] = -1
        elif key == curses.KEY_RIGHT:
            state["direction"] = 1
    return None


def monochrome_styles():
    """色が使えない端末でも、自機や重要な表示を区別する。"""
    return {
        "normal": 0, "muted": curses.A_DIM,
        "danger": curses.A_BOLD, "coin": curses.A_BOLD,
        "S": curses.A_BOLD, "M": curses.A_BOLD, "+": curses.A_BOLD,
        "player": curses.A_BOLD | curses.A_REVERSE,
    }


def setup_colors():
    """障害物は赤、取得物は種類ごとの色、自機は青地にする。"""
    styles = monochrome_styles()
    try:
        if not curses.has_colors():
            return styles
        curses.start_color()
        background = curses.COLOR_BLACK
        try:
            curses.use_default_colors()
            background = -1
        except curses.error:
            pass
        palette = [
            ("danger", curses.COLOR_RED, background),
            ("coin", curses.COLOR_YELLOW, background),
            ("S", curses.COLOR_CYAN, background),
            ("M", curses.COLOR_MAGENTA, background),
            ("+", curses.COLOR_GREEN, background),
            ("player", curses.COLOR_WHITE, curses.COLOR_BLUE),
        ]
        colored = {}
        for pair_id, (name, foreground, bg) in enumerate(palette, start=1):
            curses.init_pair(pair_id, foreground, bg)
            colored[name] = curses.color_pair(pair_id) | curses.A_BOLD
        styles.update(colored)
    except curses.error:
        # 色の初期化に失敗しても、文字と凡例だけでプレイできる。
        pass
    return styles


def draw_text(screen, y, x, text, style=0):
    """半角文字で表示し、右端と最下行には書き込まない。"""
    rows, cols = screen.getmaxyx()
    if not (0 <= y < rows - 1 and 0 <= x < cols - 1):
        return x
    # Windowsのcursesでは全角文字の幅が不安定なため、UIはASCIIで統一。
    clipped = str(text)[:cols - x - 1]
    if clipped:
        screen.addstr(y, x, clipped, style)
    return x + len(clipped)


def draw_parts(screen, y, x, parts):
    """同じ行に、色の異なる文字列を並べる。"""
    for text, style in parts:
        x = draw_text(screen, y, x, text, style)


def draw_line(screen, y, text, style=0):
    draw_text(screen, y, 1, text, style)


def record_result(state):
    """完走した1回の成績から、難易度別に各項目の最高値を保存する。"""
    try:
        RECORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(RECORDS_PATH, timeout=1.0)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS bests (
                difficulty TEXT PRIMARY KEY, score INTEGER, distance INTEGER, coins INTEGER
            )""")
            db.execute("""INSERT INTO bests (difficulty, score, distance, coins) VALUES (?, ?, ?, ?)
                ON CONFLICT(difficulty) DO UPDATE SET
                    score = MAX(score, excluded.score), distance = MAX(distance, excluded.distance),
                    coins = MAX(coins, excluded.coins)""",
                (state["difficulty"], state["score"], state["scroll_count"], state["coins_collected"]))
            return db.execute("SELECT score, distance, coins FROM bests WHERE difficulty = ?",
                              (state["difficulty"],)).fetchone()
    except (OSError, sqlite3.Error):
        return None


def draw_results(screen, state, styles):
    height, width = screen.getmaxyx()
    x = (width - 36) // 2
    y = (height - 13) // 2
    draw_text(screen, y, x, f"RUN RESULTS   /   {state['difficulty'].upper()}", curses.A_BOLD)
    draw_text(screen, y + 1, x, f"GAME OVER   {state['game_over_reason']}", styles["danger"])
    draw_text(screen, y + 3, x, f"{'':12}{'THIS RUN':>10}{'BEST':>12}", styles["muted"])
    bests = state["personal_bests"] or ("--", "--", "--")
    metrics = (("SCORE", state["score"]), ("DISTANCE", state["scroll_count"]),
               ("COINS", state["coins_collected"]))
    for i, ((label, value), best) in enumerate(zip(metrics, bests)):
        draw_text(screen, y + 4 + i, x, f"{label:12}{value:>10}{best:>12}")
    if state["personal_bests"] is None:
        draw_text(screen, y + 9, x, "Best records unavailable", styles["muted"])
    draw_text(screen, y + 12, x, "R  Race again       Q  Quit", curses.A_BOLD)


def draw_game(screen, state, styles=None):
    """Stateの内容を読み取り、文字で画面を再描画する。"""
    screen.erase()
    if styles is None:
        styles = monochrome_styles()
    if state["status"] == STATUS_GAME_OVER and state["shake_timer"] <= 0:
        draw_results(screen, state, styles)
        screen.refresh()
        return
    rows, cols = screen.getmaxyx()
    width = state["field_width"]
    offset = (cols - width) // 2
    # ゲームフィールドだけを左右に1文字揺らす。判定座標は変えない。
    shake_x = 0
    if state["shake_timer"] > 0:
        shake_x = 1 if int(state["shake_timer"] * 30) % 2 == 0 else -1
    field_offset = int(clamp(offset + shake_x, 0, max(0, cols - width - 1)))

    t = state["elapsed_time"]
    mins, seconds = divmod(int(t), 60)
    # 最優先のライフを左上に固定し、失った分は空の枠にする。
    life_style = styles["+"] if state["lives"] == MAX_LIVES else (
        styles["coin"] if state["lives"] > 1 else styles["danger"]
    )
    life_parts = [("LIFE ", curses.A_BOLD)]
    for index in range(MAX_LIVES):
        full = index < state["lives"]
        life_parts.append(("[#]" if full else "[ ]", life_style if full else styles["muted"]))
    life_parts.extend([
        (f" {state['lives']}/{MAX_LIVES}", life_style),
        (f"  SCORE {state['score']:05d}  LV {state['level']:02d}", curses.A_BOLD),
    ])
    if state["lives"] == 1:
        life_parts.append(("  LOW!", styles["danger"]))
    draw_parts(screen, 0, 1, life_parts)

    slow = f"{state['slow_timer']:.1f}s" if state["slow_timer"] > 0 else "--"
    magnet = f"{state['magnet_timer']:.1f}s" if state["magnet_timer"] > 0 else "--"
    effect_parts = [
        ("S SLOW x0.5: ", styles["S"]),
        (slow, styles["S"] if state["slow_timer"] > 0 else styles["muted"]),
        ("    M MAGNET: ", styles["M"]),
        (magnet, styles["M"] if state["magnet_timer"] > 0 else styles["muted"]),
    ]
    if state["invincible_timer"] > 0 and state["status"] != STATUS_GAME_OVER:
        effect_parts.append((f"    SAFE {state['invincible_timer']:.1f}s", styles["coin"]))
    draw_parts(screen, 1, 1, effect_parts)

    turn = "LEFT" if state["direction"] == -1 else "RIGHT"
    difficulty = state["difficulty"].upper()
    info = (
        f"DIST {state['scroll_count']:05d}  TIME {mins:02d}:{seconds:02d}  "
        f"SPEED {state['speed']:.2f}x  {turn}  {difficulty}"
    )
    draw_line(screen, 2, info, styles["muted"])
    draw_text(screen, FIELD_TOP - 1, offset, "-" * width, styles["muted"])

    player_x = int(round(state["x"]))
    for i, row in enumerate(state["rows"]):
        y = FIELD_TOP + i
        # コース外を記号で埋めず、危険な境界だけを描画する。
        draw_text(screen, y, field_offset + row["left"], "*", styles["danger"])
        draw_text(screen, y, field_offset + row["right"], "*", styles["danger"])
        if row["tree"] is not None:
            draw_text(screen, y, field_offset + row["tree"], "A", styles["danger"])
        if row["coin"] is not None:
            draw_text(screen, y, field_offset + row["coin"], "@", styles["coin"])
        if row["item"] is not None:
            item = row["item"]
            draw_text(screen, y, field_offset + item["x"], item["kind"], styles[item["kind"]])
        if row["snowball"] is not None:
            snow_x = int(round(row["snowball"]["x"]))
            draw_text(screen, y, field_offset + snow_x, "o", styles["danger"])
        if i == state["y"] and 0 <= player_x < width:
            player_icon = "O"
            if state["status"] == STATUS_GAME_OVER:
                player_icon = "X"
            elif state["invincible_timer"] > 0 and int(state["elapsed_time"] * 10) % 2:
                player_icon = "."  # 無敵中は点滅
            player_style = styles["danger"] | curses.A_REVERSE if state["status"] == STATUS_GAME_OVER else styles["player"]
            draw_text(screen, y, field_offset + player_x, player_icon, player_style)

    # 凡例の文字・色をフィールドと一致させ、プレイ中も常に表示する。
    draw_parts(screen, rows - 5, 1, [
        ("AVOID (-1 LIFE): ", styles["danger"]),
        ("A TREE  o SNOWBALL  * CLIFF", styles["danger"]),
        ("  |  ", styles["normal"]),
        ("O", styles["player"]), (" YOU", styles["normal"]),
    ])
    draw_parts(screen, rows - 4, 1, [
        ("GET: ", curses.A_BOLD),
        ("@ +100  ", styles["coin"]),
        ("S SLOW(5s)  ", styles["S"]),
        ("M MAGNET(8s)  ", styles["M"]),
        ("+ HEAL(+1)", styles["+"]),
    ])

    if state["status"] == STATUS_READY:
        message = "SPACE: start  |  N: normal / H: hard"
    elif state["status"] == STATUS_PAUSED:
        message = "PAUSED - Press SPACE to resume"
    elif state["status"] == STATUS_GAME_OVER:
        message = f"GAME OVER ({state['game_over_reason']}) - R to restart"
    else:
        message = "S: half speed / M: coin magnet / +: restore life"
    message_style = styles["danger"] if state["status"] == STATUS_GAME_OVER else curses.A_BOLD
    draw_line(screen, rows - 3, message, message_style)
    draw_line(screen, rows - 2, "LEFT/RIGHT: turn | SPACE: start/pause/resume | Q: quit", styles["muted"])
    screen.refresh()


def run(screen):
    """ゲーム全体のループ。"""
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.keypad(True)
    screen.nodelay(True)
    styles = setup_colors()

    rng = random.Random()
    state = None
    current_size = None
    last_time = time.monotonic()

    while True:
        now = time.monotonic()
        dt = min(0.10, now - last_time)
        last_time = now
        height, width = screen.getmaxyx()
        key = screen.getch()

        if key in (ord("q"), ord("Q")):
            break
        if width < MIN_COLUMNS or height < MIN_LINES:
            screen.erase()
            draw_line(screen, 1, f"Terminal too small: {width}x{height}")
            draw_line(screen, 3, f"Please enlarge to {MIN_COLUMNS}x{MIN_LINES} or more.")
            draw_line(screen, 5, "Press Q to quit.")
            screen.refresh()
            if state and state["status"] == STATUS_GAME_OVER:
                state["shake_timer"] = 0.0
            else:
                state = None
            current_size = None
            time.sleep(1.0 / FPS)
            continue

        size = (height, width)
        if state is None or size != current_size:
            field_width = min(MAX_FIELD_WIDTH, width - 4)
            field_height = height - FIELD_TOP - FOOTER_HEIGHT
            if state and state["status"] == STATUS_GAME_OVER:
                state["shake_timer"] = 0.0
            else:
                state = create_state(field_width, field_height, rng)
            current_size = size

        command = read_key(state, key)
        if command == "QUIT":
            break
        if command == "RESTART":
            state = create_state(field_width, field_height, rng, state["difficulty"])
            state["status"] = STATUS_PLAYING

        was_playing = state["status"] == STATUS_PLAYING
        update_game(state, dt, rng)
        if was_playing and state["status"] == STATUS_GAME_OVER:
            state["personal_bests"] = record_result(state)
        draw_game(screen, state, styles)
        time.sleep(1.0 / FPS)


def main():
    try:
        curses.wrapper(run)
    except curses.error as error:
        print("ターミナルの表示に失敗しました。VS Codeの『ターミナル』で実行してください。")
        print("ターミナルの幅・高さも確認してください。")
        print(f"詳細: {error}")


if __name__ == "__main__":
    main()
