from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path('/Users/nathanielkong/Documents/showcase project')
OUTPUT = ROOT / 'output/pdf/NathanielKong_CV_Analyq.pdf'
WIDTH, HEIGHT = A4
LEFT, RIGHT = 42, WIDTH - 42
TEXT_WIDTH = RIGHT - LEFT
INK = colors.HexColor('#23282B')
BLUE = colors.HexColor('#153C64')
c = canvas.Canvas(str(OUTPUT), pagesize=A4)
c.setTitle('Nathaniel Kong - Software, AI and Machine Learning CV')
c.setAuthor('Nathaniel Kong')
y = HEIGHT - 25
body = ParagraphStyle('body', fontName='Helvetica', fontSize=8.8,
                      leading=10.9, textColor=INK)
bullet_style = ParagraphStyle('bullet', parent=body, leftIndent=9,
                              firstLineIndent=-7)


def paragraph(text, style=body, after=0):
    global y
    p = Paragraph(text, style)
    _, height = p.wrap(TEXT_WIDTH, 1000)
    p.drawOn(c, LEFT, y - height)
    y -= height + after


def section(title):
    global y
    y -= 9
    c.setFillColor(BLUE)
    c.setFont('Helvetica-Bold', 9.2)
    c.drawString(LEFT, y - 9.2, title)
    y -= 12.5
    c.setStrokeColor(colors.HexColor('#A2ADB6'))
    c.setLineWidth(.35)
    c.line(LEFT, y, RIGHT, y)
    y -= 4


def heading(left, right=None):
    global y
    c.setFillColor(INK)
    c.setFont('Helvetica-Bold', 9.1)
    c.drawString(LEFT, y - 9.1, left)
    if right:
        c.setFont('Helvetica', 8.8)
        c.drawRightString(RIGHT, y - 9.1, right)
    y -= 12


def bullets(items):
    for item in items:
        paragraph('- ' + item, bullet_style, after=.4)


paragraph('NATHANIEL KONG', ParagraphStyle('name', parent=body, fontName='Helvetica-Bold',
                                        fontSize=18, leading=22, alignment=TA_CENTER), 3)
paragraph('+61435218600 | <link href="mailto:nathanielkong1@gmail.com">nathanielkong1@gmail.com</link>'
          ' | <link href="https://github.com/nathanielkong" color="#153C64"><u>github.com/nathanielkong</u></link>',
          ParagraphStyle('contact', parent=body, alignment=TA_CENTER), 4)
c.setStrokeColor(colors.HexColor('#A2ADB6'))
c.setLineWidth(.4)
c.line(LEFT, y, RIGHT, y)

section('PROFESSIONAL SUMMARY')
paragraph('Final-year Computer Science student at RMIT University focused on software engineering, artificial intelligence and machine learning. '
          'Experience building full-stack applications with React, TypeScript, Python, FastAPI, Java, Spring Boot, PostgreSQL and Docker, '
          'including LLM integration and time-series machine learning. Interested in building reliable, customer-focused solutions.')

section('EXPERIENCE')
heading('Software Engineer (Contract)', 'Jan 2026 - Apr 2026')
paragraph('1oak Marketing and Agency Company | Malaysia', after=1)
paragraph('Client website designed and developed: <link href="https://thehouseofvows.netlify.app" color="#153C64"><u>The House of Vows - thehouseofvows.netlify.app</u></link>', after=1)
bullets([
    'Delivered <b>2 client websites</b>, including The House of Vows using Next.js, React and TypeScript; translated client requirements and feedback into responsive pages and enquiry pathways.',
    'Implemented page metadata, JSON-LD and an XML sitemap; achieved Lighthouse scores of <b>91/100 SEO, 91/100 accessibility and 100/100 best practices</b> for The House of Vows.',
    'Managed Git/GitHub version control, Netlify deployment and post-launch refinements, taking projects from client brief to live website.',
])

section('PROJECTS')
heading('Analyq - Full-Stack AI Stock Research Platform')
paragraph('React | TypeScript | Python / FastAPI | PostgreSQL | scikit-learn | Gemini API | Docker | GitHub Actions', after=1)
bullets([
    'Built a full-stack stock research app integrating <b>3 APIs</b> (Alpaca, Alpha Vantage and Gemini), with interactive charts, Google/password authentication and persistent chat history.',
    'Connected LLM prompt interpretation to backend analytics; generated answers from retrieved market data and calculated metrics, caching daily reports across chat sessions to avoid repeated collection and generation.',
    'Engineered momentum, volatility, volume and benchmark features, with optional VADER news sentiment; trained logistic regression for <b>1-, 3- and 5-session</b> direction using gap-aware walk-forward validation.',
    'In a <b>6-stock audit</b>, tuned regularization to lower mean Brier score from <b>0.2958 to 0.2667</b>; retained no-edge outputs because the models did not beat naive baselines.',
    'Built a backend test suite with <b>203 tests passing in Docker</b>; containerized the frontend, API and PostgreSQL and configured GitHub Actions for CI, image publishing and deployment.',
])
y -= 5
heading('AI Blockchain Scam Detection Assistant - Final Year Project')
paragraph('Python | REST APIs | OpenAI API | Blockchain APIs', after=1)
bullets([
    'Developing an AI-assisted platform to analyse cryptocurrency wallets, tokens and transactions for scam-risk indicators.',
    'Integrating blockchain REST APIs and an LLM to collect risk signals and explain technical indicators in plain language.',
    'Designing modular backend services to support additional blockchain data providers and detection rules.',
])
y -= 5
heading('EventHub - Full-Stack Event Management Platform')
paragraph('Next.js | React | TypeScript | Java / Spring Boot | REST APIs | PostgreSQL | Docker | JUnit', after=1)
bullets([
    'Built <b>6 React/TypeScript components</b> and the Next.js frontend structure for event discovery and attendee workflows in a <b>5-person team</b>.',
    'Connected discovery and RSVP workflows to <b>4 Spring Boot REST endpoints</b>, using typed models, registration-status updates and HTTP error handling.',
    'Implemented shareable event-detail routes and drag-and-drop image previews with file-type checks and object URL cleanup.',
    'Ran the frontend and backend in <b>2 Docker containers</b>; team CI used GitHub Actions to run JUnit tests before backend image builds.',
])

section('TECHNICAL SKILLS')
for item in [
    '<b>Languages:</b> Python, Java, TypeScript, JavaScript, SQL, C++',
    '<b>Frameworks &amp; Libraries:</b> React, Next.js, FastAPI, Spring Boot, Node.js, SQLAlchemy, JUnit, pytest',
    '<b>AI &amp; Machine Learning:</b> scikit-learn, logistic regression, feature engineering, time-series validation, LLM APIs, VADER',
    '<b>Databases:</b> PostgreSQL | <b>DevOps:</b> Docker, Docker Compose, Git, GitHub Actions, CI/CD',
    '<b>Other:</b> REST APIs, HTML/CSS, Figma',
]:
    paragraph(item)

section('EDUCATION')
heading('RMIT University | Melbourne, Australia', '2023 - 2026')
paragraph('Bachelor of Computer Science')
paragraph('Focus: Artificial Intelligence, Machine Learning &amp; Full-Stack Development')
paragraph('Relevant Coursework: Full Stack Development, Machine Learning, Practical Data Science, '
          'Advanced Programming for Data Science, Algorithms &amp; Analysis, C++ Bootcamp')

section('CERTIFICATIONS')
paragraph('<b>AWS Certified Cloud Practitioner</b> | Amazon Web Services | October 2026')

assert y >= 28, f'Content is too close to the page bottom: {y:.1f}pt'
c.showPage()
c.save()
print(f'Created one-page CV; bottom margin {y:.1f}pt')
