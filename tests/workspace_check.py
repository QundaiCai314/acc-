"""Browser regression for floating windows; run against the local static preview."""
from pathlib import Path
from ui_fixture import load_ui_fixture

from playwright.sync_api import expect, sync_playwright


def move(page, selector, dx, dy):
    box = page.locator(selector).bounding_box()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.mouse.down()
    page.mouse.move(box['x'] + box['width'] / 2 + dx, box['y'] + box['height'] / 2 + dy, steps=12)
    page.mouse.up()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto('http://127.0.0.1:8080/#command')
        page.wait_for_load_state('networkidle')
        load_ui_fixture(page)
        window = page.locator('[data-window=time]')
        before = window.bounding_box()
        move(page, '[data-window=time] h2', 170, -120)
        after = window.bounding_box()
        assert abs(after['x'] - before['x'] - 170) < 2, ('Title must drag window', before, after)
        assert abs(after['y'] - before['y'] + 120) < 2
        assert not page.locator('.is-dragging').count()
        # Keyboard movement, minimization, restore, and same-session placement.
        page.locator('[data-drag-window=time]').focus()
        page.keyboard.press('ArrowRight')
        expect(window).to_have_css('left', str(round(after['x'] + 16)) + 'px')
        saved = window.bounding_box()
        window.locator('[data-action=minimize-window]').click()
        expect(window).to_have_count(0)
        page.locator('[data-action=restore-window][data-window-id=time]').click()
        assert abs(window.bounding_box()['x'] - saved['x']) < 2
        # Reopening via dock must also remove the minimized entry.
        window.locator('[data-action=minimize-window]').click()
        page.locator('.map-tool-dock [data-action=toggle-time]').click()
        expect(page.locator('[data-action=restore-window][data-window-id=time]')).to_have_count(0)
        # Clamp to the workspace, not merely to the edge of the title.
        move(page, '[data-window=time] h2', -1600, -1600)
        rect = window.bounding_box()
        stage = page.locator('.workspace-stage').bounding_box()
        assert rect['x'] >= stage['x'] and rect['y'] >= stage['y']
        move(page, '[data-window=time] h2', 2000, 2000)
        rect = window.bounding_box()
        assert rect['x'] + rect['width'] <= stage['x'] + stage['width'] + 1
        assert rect['y'] + rect['height'] <= stage['y'] + stage['height'] + 1
        page.locator('.map-tool-dock [data-action=toggle-time]').click()
        for action, name in [('toggle-data', 'data'), ('toggle-objects', 'objects'), ('toggle-layers', 'layers'), ('toggle-graph', 'graph'), ('toggle-intel', 'intel')]:
            page.locator('.map-tool-dock [data-action=' + action + ']').click()
            panel = page.locator('[data-window=' + name + ']')
            before = panel.bounding_box()
            move(page, '[data-window=' + name + '] .window-bar h2', 24, 24)
            after = panel.bounding_box()
            assert after != before, name
            panel.locator('.window-actions button').last.click()
        # Workflow tabs retain review edits; dragging never replaces the form.
        page.locator('.primary-modes a[href="#analysis"]').click()
        page.locator('.workflow-tabs a[href="#review"]').click()
        note = page.locator('#review-form [name=note]')
        note.fill('Window regression draft')
        annotation = page.evaluate("async () => (await import('./state.js')).state.annotationId")
        move(page, '[data-window=tool] h1', 45, 40)
        expect(note).to_have_value('Window regression draft')
        page.locator('[data-drag-window=tool]').focus()
        page.keyboard.press('ArrowRight')
        assert page.evaluate("async () => (await import('./state.js')).state.annotationId") == annotation
        page.locator('[data-action=expand-tool]').click()
        assert page.locator('[data-window=tool]').bounding_box()['width'] > 1400
        page.locator('[data-action=expand-tool]').click()
        page.locator('[data-window=tool] [data-action=minimize-window]').click()
        expect(page.locator('[data-window=tool]')).to_have_count(0)
        page.locator('[data-action=restore-window][data-window-id=tool]').click()
        expect(note).to_have_value('Window regression draft')
        # Full viewport screenshots are intentional: WebGL uses fixed viewport dimensions.
        output = Path('data/frontend-check')
        output.mkdir(parents=True, exist_ok=True)
        for width in (320, 768, 1024, 1440):
            page.set_viewport_size({'width': width, 'height': 1000})
            for route in ('command', 'analysis', 'review', 'registration', 'plans'):
                page.goto('http://127.0.0.1:8080/#' + route)
                page.wait_for_load_state('networkidle')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, route)
                if route != 'command':
                    panel = page.locator('[data-window=tool]').bounding_box()
                    assert panel['x'] >= 0 and panel['x'] + panel['width'] <= width + 1, (width, route, panel)
                page.screenshot(path=str(output / f'workspace-{route}-{width}.png'))
        assert not errors, errors
        browser.close()
    print('PASS: title dragging, keyboard, bounds, minimize/restore, tabs/drafts, expansion and four viewport sizes.')


if __name__ == '__main__':
    main()
