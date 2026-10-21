"""Theme integration: rendering, responsive controls, drafts and optional axe-core."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--axe', type=Path)
    args = parser.parse_args()
    output = Path('data/frontend-check')
    output.mkdir(parents=True, exist_ok=True)
    violations = []
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:8080/#review')
        page.wait_for_load_state('networkidle')
        grid = page.evaluate("""async () => {
            const {state} = await import('./state.js'), {mapData} = await import('./gis.js');
            const dataset = state.dataset;
            const populated = mapData().grid.features;
            try {
                state.dataset = null;
                return {count: populated.length, finite: populated.every(f => f.geometry.coordinates.flat().every(Number.isFinite)), empty: mapData().grid.features.length};
            } finally { state.dataset = dataset; }
        }""")
        assert grid == {'count': 34, 'finite': True, 'empty': 0}, grid
        note = page.locator('#review-form [name=note]')
        note.fill('Theme change keeps reviewer draft')
        identity = page.evaluate("async () => (await import('./state.js')).state.identity")
        for theme in ('brutalist', 'mineral', 'vellum'):
            page.set_viewport_size({'width': 1440, 'height': 1000})
            page.goto('http://127.0.0.1:8080/#review')
            page.wait_for_load_state('networkidle')
            page.locator('[data-action=art-theme][data-value=' + theme + ']').click()
            expect(page.locator('html')).to_have_attribute('data-theme', theme)
            expect(note).to_have_value('Theme change keeps reviewer draft')
            assert page.evaluate("async () => (await import('./state.js')).state.identity") == identity
            assert page.evaluate("document.activeElement.dataset.value") == theme
            for route in ('login', 'command', 'import', 'analysis', 'review', 'registration', 'plans', 'reason', 'field'):
                page.goto('http://127.0.0.1:8080/#' + route)
                page.wait_for_load_state('networkidle')
                if args.axe:
                    page.add_script_tag(path=str(args.axe))
                    found = page.evaluate("async () => (await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})).violations")
                    if found:
                        violations.append({'theme': theme, 'route': route, 'violations': found})
                if route in ('command', 'review', 'registration'):
                    page.screenshot(path=str(output / f'atlas-{theme}-{route}.png'))
            for width in (320, 768, 1024, 1440):
                page.set_viewport_size({'width': width, 'height': 1000})
                page.goto('http://127.0.0.1:8080/#login')
                expect(page.locator('.ds-login-title')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), ('login', theme, width)
                for control in page.locator('#login-form input:visible, .ds-submit-btn:visible').all():
                    box = control.bounding_box()
                    assert box and box['x'] >= 0 and box['x'] + box['width'] <= width + 1, ('login', theme, width, box)
                page.get_by_role('button', name='注册').click()
                expect(page.locator('#register-account-form')).to_be_visible()
                expect(page.get_by_role('button', name='提交注册申请')).to_be_visible()
                page.get_by_role('button', name='登录').click()
                expect(page.get_by_role('button', name='主视觉 2（待补充）', exact=True)).to_be_disabled()
                expect(page.get_by_role('button', name='主视觉 3（待补充）', exact=True)).to_be_disabled()
                expect(page.get_by_role('button', name='主视觉 4（待补充）', exact=True)).to_be_disabled()
                page.get_by_role('button', name='主视觉 1', exact=True).click()
                art = page.locator('.ds-login-art')
                expect(art).to_be_visible()
                assert art.evaluate('(img) => img.complete && img.naturalWidth === 1086 && img.naturalHeight === 1448')
                rect = page.locator('.ds-login-right').bounding_box()
                image_rect = art.bounding_box()
                assert all(abs(rect[k] - image_rect[k]) < 1 for k in ('x', 'y', 'width', 'height')), (rect, image_rect)
                if width > 860:
                    assert abs(rect['width'] - width / 2) < 1, rect
                if theme == 'vellum' and width in (320, 1440):
                    page.screenshot(path=str(output / ('login-mobile.png' if width == 320 else 'login-desktop.png')), full_page=True)
                page.goto('http://127.0.0.1:8080/#command')
                page.wait_for_load_state('networkidle')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (theme, width)
                for control in page.locator('.primary-modes a, .art-switcher button, .connection').all():
                    box = control.bounding_box()
                    assert box and box['x'] >= 0 and box['y'] >= 0 and box['x'] + box['width'] <= width + 1, (theme, width, box)
                page.screenshot(path=str(output / f'atlas-{theme}-{width}.png'))
            print('Checked', theme, flush=True)
        browser.close()
    (output / 'theme-accessibility.json').write_text(json.dumps(violations, ensure_ascii=False, indent=2), encoding='utf-8')
    for row in violations:
        print(row['theme'], row['route'], [(v['id'], [n['target'] for n in v['nodes']]) for v in row['violations']])
    assert not violations, 'See data/frontend-check/theme-accessibility.json'
    assert not errors, errors
    print('PASS: three themes, drafts, identity, focus, responsive controls, local grid and browser errors.')


if __name__ == '__main__':
    main()
