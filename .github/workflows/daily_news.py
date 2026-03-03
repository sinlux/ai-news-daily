#!/usr/bin/env python3
"""
AI新闻日报生成器 - GitHub Actions 版本
使用 OpenAI API 替代本地 Ollama
"""

import os
import sys
import hashlib
import feedparser
import requests
from datetime import datetime
from dateutil import parser as date_parser

# 配置
EMAIL_ENABLED = True
EMAIL_SMTP_HOST = "smtp.qq.com"
EMAIL_SMTP_PORT = 465
EMAIL_SENDER = "908827397@qq.com"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")  # 从环境变量读取
EMAIL_RECEIVER = "market@sinluxlight.com"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # OpenAI API Key
USE_OPENAI = bool(OPENAI_API_KEY)

MAX_ARTICLES_PER_CATEGORY = 5  # 每个分类最多5条
HOURS_BACK = 48

# 新闻源
RSS_SOURCES = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "weight": 5},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "weight": 4},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "weight": 4},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "weight": 5},
    {"name": "AI News", "url": "https://www.artificialintelligence-news.com/feed/", "weight": 4},
    {"name": "THE DECODER", "url": "https://the-decoder.com/feed/", "weight": 4},
    {"name": "GitHub Blog", "url": "https://github.blog/feed/", "weight": 4},
    {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml", "weight": 4},
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "weight": 3},
]

CATEGORY_KEYWORDS = {
    "智能体/Agent": ["agent", "agents", "autonomous", "crewai", "autogpt"],
    "工作流自动化": ["workflow", "automation", "n8n", "zapier", "make", "rpa"],
    "AI建站": ["website", "builder", "framer", "webflow", "vercel", "no-code"],
    "AI客服": ["customer", "chatbot", "support", "service"],
    "AI营销": ["marketing", "sales", "crm", "hubspot"],
    "大模型": ["gpt", "claude", "llm", "model", "gemini", "llama"],
    "开源项目": ["open source", "github", "repository"],
    "融资动态": ["funding", "million", "billion", "invest", "startup"],
    "产品发布": ["launch", "release", "announce", "product"],
}

IMPORTANT_KEYWORDS = {
    "gpt": 5, "openai": 5, "claude": 5, "anthropic": 4, "gemini": 4,
    "llama": 4, "automation": 5, "workflow": 5, "agent": 5,
    "github": 4, "funding": 4, "billion": 5, "launch": 4,
}


class NewsFetcher:
    def fetch_source(self, source):
        try:
            print(f"  📡 抓取: {source['name']}...")
            feed = feedparser.parse(source['url'])
            articles = []
            
            for entry in feed.entries[:10]:
                pub_date = None
                if hasattr(entry, 'published'):
                    try:
                        pub_date = date_parser.parse(entry.published)
                    except:
                        pass
                
                if pub_date:
                    hours_ago = (datetime.now(pub_date.tzinfo) - pub_date).total_seconds() / 3600
                    if hours_ago > HOURS_BACK:
                        continue
                
                articles.append({
                    'title': entry.get('title', '').strip(),
                    'link': entry.get('link', ''),
                    'summary': entry.get('summary', entry.get('description', '')),
                    'source': source['name'],
                    'source_weight': source.get('weight', 1),
                    'published': pub_date.strftime('%Y-%m-%d %H:%M') if pub_date else '未知',
                })
                
            print(f"     ✓ {len(articles)} 条")
            return articles
        except Exception as e:
            print(f"     ✗ {e}")
            return []


class ContentProcessor:
    def __init__(self):
        self.seen_hashes = set()
        
    def deduplicate(self, articles):
        unique = []
        for article in articles:
            h = hashlib.md5(article['title'][:30].lower().encode()).hexdigest()[:12]
            if h not in self.seen_hashes:
                self.seen_hashes.add(h)
                article['hash'] = h
                unique.append(article)
        return unique
    
    def process(self, articles):
        articles = self.deduplicate(articles)
        for article in articles:
            score = article.get('source_weight', 1) * 2
            title_lower = article['title'].lower()
            for keyword, weight in IMPORTANT_KEYWORDS.items():
                if keyword in title_lower:
                    score += weight
            article['score'] = min(score, 20)
            
            # 分类
            text = (article['title'] + " " + article.get('summary', '')).lower()
            article['category'] = "其他"
            for cat, keywords in CATEGORY_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    article['category'] = cat
                    break
        
        # 按分类分组并排序，每个分类取前5条
        by_category = {}
        for article in articles:
            cat = article.get('category', '其他')
            by_category.setdefault(cat, []).append(article)
        
        # 每个分类按热度排序，取前5条
        result = []
        for cat in by_category:
            by_category[cat].sort(key=lambda x: x['score'], reverse=True)
            result.extend(by_category[cat][:MAX_ARTICLES_PER_CATEGORY])
        
        # 整体按分数排序
        result.sort(key=lambda x: x['score'], reverse=True)
        return result


class Summarizer:
    def summarize(self, title, content):
        """使用 OpenAI API 或简单截断"""
        if USE_OPENAI:
            return self._openai_summarize(title, content)
        else:
            # 无API时使用简单处理
            return title, content[:100] + "..."
    
    def _openai_summarize(self, title, content):
        try:
            content = content[:1500] if content else title
            prompt = f"""将以下英文AI新闻翻译成中文：

标题: {title}
内容: {content}

输出格式:
中文标题: [翻译后的中文标题]
摘要: [1-3句话中文摘要，简洁明了]"""

            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3
                },
                timeout=30
            )
            result = resp.json()
            text = result['choices'][0]['message']['content']
            
            # 解析
            chinese_title = title
            summary = content[:100]
            for line in text.split('\n'):
                if '中文标题:' in line or '中文标题：' in line:
                    chinese_title = line.split(':', 1)[-1].strip()
                elif '摘要:' in line or '摘要：' in line:
                    summary = line.split(':', 1)[-1].strip()
            
            return chinese_title, summary
        except Exception as e:
            print(f"     ⚠️ API失败: {e}")
            return title, content[:100] + "..."


class EmailSender:
    def send(self, subject, content):
        if not EMAIL_PASSWORD:
            print("⚠️  无邮箱授权码")
            return
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.utils import formataddr
            
            msg = MIMEMultipart('alternative')
            msg['From'] = formataddr(("AI日报", EMAIL_SENDER))
            msg['To'] = EMAIL_RECEIVER
            msg['Subject'] = subject
            
            # 转换为HTML格式，支持高亮样式
            html_content = self._markdown_to_html(content)
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            server = smtplib.SMTP_SSL(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT)
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, [EMAIL_RECEIVER], msg.as_string())
            server.quit()
            print("✅ 邮件发送成功!")
        except Exception as e:
            print(f"❌ 邮件失败: {e}")
    
    def _markdown_to_html(self, md_content):
        """将Markdown转换为HTML，分类标题加大加粗高亮"""
        import re
        
        lines = md_content.split('\n')
        html_lines = [
            '<html><head><meta charset="utf-8"><style>',
            'body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }',
            'h1 { color: #1a1a1a; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }',
            'h2 { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 20px; border-radius: 8px; font-size: 18px; font-weight: bold; margin-top: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }',
            'h3 { color: #2c3e50; font-size: 16px; margin-top: 20px; }',
            'p { margin: 10px 0; }',
            'blockquote { border-left: 4px solid #4CAF50; margin: 10px 0; padding-left: 15px; color: #666; }',
            'a { color: #4CAF50; text-decoration: none; }',
            'a:hover { text-decoration: underline; }',
            'hr { border: none; border-top: 1px solid #eee; margin: 20px 0; }',
            '.score { color: #ff9800; font-weight: bold; }',
            '</style></head><body>'
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # H1
            if line.startswith('# '):
                text = line[2:]
                html_lines.append(f'<h1>{text}</h1>')
            # H2 - 分类标题
            elif line.startswith('## '):
                text = line[3:]
                html_lines.append(f'<h2>📁 {text}</h2>')
            # H3 - 新闻标题
            elif line.startswith('### '):
                text = line[4:]
                html_lines.append(f'<h3>📰 {text}</h3>')
            # 引用块
            elif line.startswith('> '):
                text = line[2:]
                # 转换链接
                text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
                # 高亮分数
                text = re.sub(r'⭐(\d+)', r'<span class="score">⭐\1</span>', text)
                html_lines.append(f'<blockquote>{text}</blockquote>')
            # 分隔线
            elif line == '---':
                html_lines.append('<hr>')
            else:
                html_lines.append(f'<p>{line}</p>')
        
        html_lines.append('</body></html>')
        return '\n'.join(html_lines)


def main():
    print("=" * 50)
    print("🤖 AI新闻日报 - GitHub Actions")
    print("=" * 50)
    
    # 抓取
    fetcher = NewsFetcher()
    all_articles = []
    for source in RSS_SOURCES:
        all_articles.extend(fetcher.fetch_source(source))
    print(f"\n✅ 共抓取 {len(all_articles)} 条")
    
    if not all_articles:
        print("⚠️ 无新闻")
        return
    
    # 处理
    processor = ContentProcessor()
    articles = processor.process(all_articles)
    print(f"📊 精选 {len(articles)} 条")
    
    # 摘要
    summarizer = Summarizer()
    for i, article in enumerate(articles, 1):
        print(f"   [{i}/{len(articles)}] {article['title'][:40]}...")
        chinese_title, summary = summarizer.summarize(article['title'], article.get('summary', ''))
        article['chinese_title'] = chinese_title
        article['ai_summary'] = summary
    
    # 生成报告
    os.makedirs("output", exist_ok=True)
    date_str = datetime.now().strftime('%Y年%m月%d日')
    filename = f"output/{datetime.now().strftime('%Y-%m-%d')}_AI日报.md"
    
    lines = [f"# 🤖 AI日报 - {date_str}", "", f"> 共 {len(articles)} 条", "", "---", ""]
    
    by_category = {}
    for article in articles:
        cat = article.get('category', '其他')
        by_category.setdefault(cat, []).append(article)
    
    for cat, items in by_category.items():
        lines.extend([f"## {cat}", ""])
        for article in items:
            title = article.get('chinese_title', article['title'])
            lines.extend([
                f"### {title}",
                "",
                f"{article.get('ai_summary', '暂无')}",
                "",
                f"> [原文]({article['link']}) | {article['source']} | ⭐{article['score']}",
                "",
                "---",
                ""
            ])
    
    content = '\n'.join(lines)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✅ 已生成: {filename}")
    
    # 发送邮件
    EmailSender().send(f"🤖 AI日报 - {date_str}", content)
    print("=" * 50)


if __name__ == '__main__':
    main()
