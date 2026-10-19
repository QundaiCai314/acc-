"""Optional axe-core check; pass a local official axe.min.js via --axe."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--axe', required=True, type=Path)
    parser.add_argument('--url', default='http://127.0.0.1:8080')
    parser.add_argument('--channel', default='chrome')
    args = parser.parse_args()
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=args.channel)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        for route in ('command', 'import', 'analysis', 'review', 'registration', 'plans', 'reason', 'field'):
            page.goto(args.url + '/#' + route)
            page.wait_for_load_state('networkidle')
            page.add_script_tag(path=str(args.axe))
            result = page.evaluate("async () => (await axe.run(document, {runOnly:{type:'tag', values:['wcag2a','wcag2aa','wcag21aa']}})).violations")
            results.append({'route': route, 'violations': result})
        page.goto(args.url + '/#command')
        page.locator('.entity-row[data-id=building-a]').focus()
        page.keyboard.press('Enter')
        assert page.locator('.object-summary h2').inner_text().startswith('A 楼')
        page.get_by_role('button', name='连接设置').click()
        page.keyboard.press('Tab')
        assert page.evaluate('document.querySelector("#dialog").contains(document.activeElement)')
        page.keyboard.press('Escape')
        assert not page.locator('#dialog').is_visible()
        browser.close()
    output = Path('data/frontend-check/accessibility.json')
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    for result in results:
        print(result['route'], [(v['id'], len(v['nodes'])) for v in result['violations']])
    assert not any(r['violations'] for r in results), 'See data/frontend-check/accessibility.json'
    print('PASS: WCAG A/AA automated checks, entity keyboard selection, native dialog focus and Escape.')


if __name__ == '__main__':
    main()
