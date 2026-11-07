# friend-birthday-quiz

Local Kahoot-style quiz server for a friend's birthday. Single file, no dependencies, Python 3.

## Run

```bash
python3 app.py
```

- Host: open the URL printed in the terminal (`/host`) on your laptop.
- Players: same Wi-Fi, open the root URL, enter a nickname.

## Customize

- Edit `QUIZ` in `app.py` — questions about your friend. The correct answer is always the first option; they're shuffled before display.
- Keep all options similar in length and format so the correct one doesn't stand out.
- Optional photo questions: put the image in `img/` and add its filename as the 4th element of the question tuple.
- Replace `[NAME]` with your friend's name.
