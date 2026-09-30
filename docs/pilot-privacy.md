# Pilot privacy and consent note

Thank you for helping test Chief-of-Staff AI. Please read this before you take part. Taking part
is voluntary, and you can stop at any time.

## What you will do

For two weeks, you run the tool on an export of **your own** email or Slack messages, on your own
computer. It lists the tasks it finds. You open a page in your browser, mark each task as right or
wrong, add any it missed, and send back one small file.

## Use only your own personal data

- Run the tool only on messages from **your own personal accounts**.
- **Do not use your employer's Slack or email** (or any account belonging to an organisation)
  unless your employer has approved it in writing. Work accounts often carry confidentiality
  duties you cannot waive on your own.
- The messages you run it on will include other people's words. Everything about them stays on
  your computer (see below), but if an account holds messages you were asked to keep private,
  leave that account out.

## What stays on your computer

- Your messages, the tasks the tool finds, the names in them, and the review page.
- The notes you type next to missed tasks.
- With the default setting, nothing is sent over the internet at all: the tool and the review
  page both work offline.

## What you send back

Only the file the review page saves (`pilot-<your code>-<run>.json`). It contains:

- your pilot code (for example `P3`, never your name);
- for each task the tool found: its type (asked, promised, done), whether it came from email or
  Slack, whether it had an owner and a due date, its priority and confidence, and your answer;
- for each task you added as missed: its type and whether it came from email or Slack;
- counts (how many messages were scanned) and the tool version.

It contains **no message text, no names, no email addresses, no subjects, no channel names and no
message dates**. The project's report tool rejects any file that contains extra fields. You can
open the file in any text editor to check it before sending.

## Optional: using an AI model

By default the tool uses offline rules. If you choose an AI model instead (`--backend nvidia`,
`gemini` or `anthropic`, with your own API key), the text of each message is sent to that
provider after names, email addresses, phone numbers and secrets are masked. That provider's
own privacy terms then apply. Only do this if you are comfortable with it; the pilot works
without it.

## How your answers are used

The files from all participants are combined into totals: how often the tool's tasks were real,
how often the owner and date were right, and how many tasks it missed. Results are published
per pilot code and in total, never with names. With so few participants, someone who knows you
took part might guess which row is yours; the rows contain only counts.

## Stopping and deleting

You can stop at any time without giving a reason. To withdraw your answers, tell the organiser
your pilot code and the file will be deleted and left out of any report produced after that. To
remove everything from your computer, delete the pilot folder and the tool's `.cos` folder, and
clear the page's saved progress by clearing site data for the page in your browser.

## Consent

By sending your file back, you confirm that:

1. you ran the tool only on your own personal accounts, or on work accounts your employer approved;
2. you read what the file contains and are happy to share it;
3. you understand you can withdraw your answers at any time.

Questions: contact the organiser who invited you.
