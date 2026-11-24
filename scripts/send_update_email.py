"""Email a digest only after the auto-update workflow publishes new articles."""

import argparse
import json
import os
from email.message import EmailMessage
from pathlib import Path
import smtplib
import ssl
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ("求是", "data/qs/meta.json"),
    ("红旗文稿", "data/hqwg/meta.json"),
    ("党建研究", "data/meta.json"),
    ("旗帜", "data/qz/meta.json"),
    ("习近平讲话库", "data/speeches/index.json"),
)


def items_at(revision, path):
    raw = subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)
    data = json.loads(raw)
    return data["items"] if isinstance(data, dict) else data


def new_items(before, after):
    known = {item["u"] for item in before}
    return [item for item in after if item["u"] not in known]


def make_digest(changes, commit, repository, run_id):
    counts = "、".join(f"{name} {len(items)} 篇" for name, items in changes)
    subject = f"文章库更新：{counts}"
    lines = ["官网文章库已自动更新，以下内容已通过校验并推送到 GitHub。", ""]
    for name, items in changes:
        lines.append(f"{name}：新增 {len(items)} 篇")
        for item in items[:12]:
            issue = f"（{item['y']} 年第 {item['i']} 期）" if "i" in item else ""
            lines.append(f"  · {item['t']}{issue}")
        if len(items) > 12:
            lines.append(f"  · 另有 {len(items) - 12} 篇，请到网站查看")
        lines.append("")
    lines.extend([
        "阅读网站：https://paper.zhouhao.cn/",
        f"更新提交：https://github.com/{repository}/commit/{commit}",
        f"运行记录：https://github.com/{repository}/actions/runs/{run_id}",
    ])
    return subject, "\n".join(lines)


def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing GitHub Actions secret: {name}")
    return value


def main(test=False):
    changes = []
    if not test:
        for name, path in SOURCES:
            added = new_items(items_at("HEAD^", path), items_at("HEAD", path))
            if added:
                changes.append((name, added))
        if not changes:
            print("Published commit contains no new articles; no email needed.")
            return 0

    host = os.environ.get("UPDATE_MAIL_HOST") or "smtp.qq.com"
    port = int(os.environ.get("UPDATE_MAIL_PORT") or "465")
    user = required_env("UPDATE_MAIL_USER")
    password = required_env("UPDATE_MAIL_PASSWORD")
    sender = os.environ.get("UPDATE_MAIL_FROM") or user
    recipients = [address.strip() for address in (os.environ.get("UPDATE_MAIL_TO") or user).split(",") if address.strip()]
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    if test:
        subject = "文章库更新通知测试"
        body = ("这是一封手动触发的测试邮件，说明 QQ SMTP 发信已配置成功。\n"
                "正常定时检查没有新增文章时不会发邮件。\n\n"
                f"运行记录：https://github.com/{repository}/actions/runs/{run_id}")
    else:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        subject, body = make_digest(changes, commit, repository, run_id)
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as smtp:
            smtp.login(user, password)
            smtp.send_message(message)
    elif port == 587:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls(context=context)
            smtp.login(user, password)
            smtp.send_message(message)
    else:
        raise ValueError("UPDATE_MAIL_PORT must be 465 (SSL) or 587 (STARTTLS)")
    print("Sent test email." if test else f"Sent update digest for {sum(len(items) for _, items in changes)} new articles.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Send one manually requested SMTP test email")
    raise SystemExit(main(test=parser.parse_args().test))
