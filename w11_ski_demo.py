"""第11回配布教材：ASCIIスキーゲーム（学生版）。

実行：python w11_ski_demo.py
Windowsで curses が見つからない場合：py -m pip install windows-curses

w11演習01：update_distance_score() の中だけを実装する。
"""

import random
import time
from collections import deque

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
FIELD_TOP = 3
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


def clamp(value, minimum, maximum):
    """値が指定範囲からはみ出さないようにする。"""
    return max(minimum, min(value, maximum))


def create_state(field_width, field_height, rng):
    """新しいゲームを開始するためのStateを用意する。"""
    half_width = min(19, max(13, (field_width - 12) // 2))
    state = {
        "status": STATUS_READY,
        "difficulty": "normal",
        "x": field_width // 2,
        "y": max(3, int(field_height * 0.35)),
        "direction": 1,     # -1: 左、+1: 右。直進（0）は使わない。
        "speed": 1.0,
        "base_speed": 1.5,
        "elapsed_time": 0.0,   # 一時停止中は増えない
        "scroll_count": 0,    # コースが進んだ行数
        "score": 0,           # w11演習01で更新する
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

    # 開始直後の画面は障害物なし。新しく現れるコースから木を生成する。
    for _ in range(field_height):
        state["rows"].append(create_course_row(state, rng, with_tree=False))
    return state


def create_course_row(state, rng, with_tree=True):
    """コースを1行生成する。木や崖の生成は講師提供部分。"""
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
    tree = None
    tree_rate = min(0.52, 0.23 + (state["level"] - 1) * 0.055)
    if state["difficulty"] == "hard":
        tree_rate = tree_rate * 1.5
    if with_tree and rng.random() < tree_rate:
        tree = rng.randint(left + 3, right - 3)

    coin = None
    coin_rate = 0.05
    if with_tree and rng.random() < coin_rate:
        coin = rng.randint(left + 3, right - 3)
    if coin == tree:
        coin = None
        

    # 初期画面には追加の障害物やアイテムも出さない。
    occupied = {x for x in (tree, coin) if x is not None}
    available = [x for x in range(left + 3, right - 2) if x not in occupied]
    snowball = None
    if with_tree and available and rng.random() < SNOWBALL_RATE:
        snow_x = rng.choice(available)
        available.remove(snow_x)
        snowball = {"x": float(snow_x), "direction": rng.choice([-1, 1])}

    item = None
    if with_tree and available and rng.random() < ITEM_RATE:
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
    """アイテムを取得。同じ効果の再取得時は残り時間を戻す。"""
    item = row["item"]
    if item is None or item["x"] != int(round(state["x"])):
        return
    if item["kind"] == "S":
        state["slow_timer"] = SLOW_DURATION
    elif item["kind"] == "M":
        state["magnet_timer"] = MAGNET_DURATION
    elif item["kind"] == "+":
        state["lives"] = min(MAX_LIVES, state["lives"] + 1)
    row["item"] = None


def collect_coins(state):
    """通常は接触で回収。磁石使用中は周囲4マスまで回収。"""
    player_x = int(round(state["x"]))
    radius = MAGNET_RADIUS if state["magnet_timer"] > 0 else 0
    for y, row in enumerate(state["rows"]):
        if row["coin"] is None:
            continue
        distance = abs(row["coin"] - player_x) + abs(y - state["y"])
        if distance <= radius:
            state["score"] += 100
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


def draw_line(screen, y, text, style=0):
    """右下隅への書き込みによるcursesエラーを避けて表示する。"""
    rows, cols = screen.getmaxyx()
    if 0 <= y < rows - 1 and cols >= 2:
        screen.addnstr(y, 1, str(text), cols - 2, style)


def draw_game(screen, state):
    """Stateの内容を読み取り、文字で画面を再描画する。"""
    screen.erase()
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
    hud = (
        f"LV {state['level']:02d} | SCORE {state['score']:05d} | "
        f"DIST {state['scroll_count']:05d} | TIME {mins:02d}:{seconds:02d}"
    )
    turn = "LEFT" if state["direction"] == -1 else "RIGHT"
    difficulty = state["difficulty"].upper()
    info = f"SPEED {state['speed']:.2f}x | TURN {turn} | STATE {state['status']} | DIFFICULTY {difficulty}"
    draw_line(screen, 0, hud, curses.A_BOLD)
    draw_line(screen, 1, info)
    screen.addnstr(2, offset, "=" * width, width)
    effects = (
        f"LIFE {state['lives']}/{MAX_LIVES} | "
        f"S {state['slow_timer']:.1f}s | M {state['magnet_timer']:.1f}s"
    )
    draw_line(screen, rows - 4, effects, curses.A_BOLD)

    player_x = int(round(state["x"]))
    for i, row in enumerate(state["rows"]):
        chars = [" "] * width
        for x in range(0, row["left"] + 1):
            chars[x] = "*"
        for x in range(row["right"], width):
            chars[x] = "*"
        if row["tree"] is not None:
            chars[row["tree"]] = "A"
        if row["coin"] is not None:
            chars[row["coin"]] = "@"
        if row["item"] is not None:
            chars[row["item"]["x"]] = row["item"]["kind"]
        if row["snowball"] is not None:
            chars[int(round(row["snowball"]["x"]))] = "o"
        if i == state["y"] and 0 <= player_x < width:
            player_icon = "O"
            if state["status"] == STATUS_GAME_OVER:
                player_icon = "X"
            elif state["invincible_timer"] > 0 and int(state["elapsed_time"] * 10) % 2:
                player_icon = "."  # 無敵中は点滅
            chars[player_x] = player_icon
        screen.addnstr(FIELD_TOP + i, field_offset, "".join(chars), width)

    if state["status"] == STATUS_READY:
        message = "READY! Press SPACE to start"
    elif state["status"] == STATUS_PAUSED:
        message = "PAUSED - Press SPACE to resume"
    elif state["status"] == STATUS_GAME_OVER:
        message = f"GAME OVER ({state['game_over_reason']}) - R to restart"
    else:
        message = "Avoid A / * / o | Items: S=slow M=magnet +=life"
    draw_line(screen, rows - 3, message, curses.A_BOLD)
    draw_line(screen, rows - 2, "LEFT/RIGHT: switch turn | SPACE: start/pause | R: restart | Q: quit")
    screen.refresh()


def run(screen):
    """ゲーム全体のループ。"""
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.keypad(True)
    screen.nodelay(True)

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
            state = None
            current_size = None
            time.sleep(1.0 / FPS)
            continue

        size = (height, width)
        if state is None or size != current_size:
            field_width = min(MAX_FIELD_WIDTH, width - 4)
            field_height = height - 7
            state = create_state(field_width, field_height, rng)
            current_size = size

        command = read_key(state, key)
        if command == "QUIT":
            break
        if command == "RESTART":
            state = create_state(state["field_width"], state["field_height"], rng)
            state["status"] = STATUS_PLAYING

        update_game(state, dt, rng)
        draw_game(screen, state)
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
