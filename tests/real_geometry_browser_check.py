"""Read-only browser verification after importing real geometry into localhost:8000.

Requires the frontend on :8080. Never submits a live review or calls a model.
"""
import json
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


def main():
    root = Path('data/real-geometry')
    imported = json.loads((root/'live-import.json').read_text('utf8'))
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:8080/#command')
        page.wait_for_load_state('networkidle')
        page.get_by_role('button', name='连接设置').click()
        page.locator('#connect-form [name=base]').fill('http://127.0.0.1:8000')
        page.get_by_role('button', name='连接并读取现场').click()
        expect(page.locator('#dialog')).not_to_be_visible(timeout=15000)

        def select(key):
            page.locator('[data-action=datasets]').first.click()
            page.locator('#select-dataset-form select').select_option(imported[key]['id'])
            page.get_by_role('button', name='打开现场', exact=True).click()
            expect(page.locator('#dialog')).not_to_be_visible(timeout=15000)

        select('road_dataset')
        page.evaluate("location.hash='plans'")
        expect(page.locator('#route-form [name=basis]')).to_have_value('reviewed_status')
        expect(page.locator('#route-form [name=basis] option')).to_have_count(2)
        page.wait_for_load_state('networkidle')
        assert page.evaluate("async () => (await import('./gis.js')).mapData().entities.features.length") == 27
        # Pending roads must not silently appear as an approved routing layer.
        assert page.evaluate("async () => !(await import('./state.js')).activeArtifact('road_network')")
        page.locator('.artifact-detail').first.locator('summary').first.click()
        expect(page.locator('.artifact-review').first.get_by_text('候选待审', exact=True)).to_be_visible()
        page.screenshot(path=str(root/'workbench-roads.png'))

        select('scan_dataset')
        page.evaluate("location.hash='registration'")
        expect(page.locator('#scene-slot')).to_be_visible()
        expect(page.locator('#scene-slot .three-renderer canvas')).to_be_visible()
        expect(page.locator('.scene-head')).to_contain_text('XYZ')
        expect(page.locator('.table-scroll tbody tr')).to_have_count(80)
        expect(page.locator('.table-scroll thead')).to_contain_text('目标坐标 / m')
        assert page.evaluate("async () => (await import('./gis.js')).mapData().entities.features.length") == 0
        for width in (320, 768, 1024, 1440):
            page.set_viewport_size({'width': width, 'height': 1000})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        page.locator('.table-scroll button[data-action=point]').first.click()
        expect(page.locator('.table-scroll tr.selected')).to_have_count(1)
        page.locator('svg [data-action=point]').last.focus()
        page.keyboard.press('Enter')
        expect(page.locator('.table-scroll tr.selected')).to_have_count(1)
        page.screenshot(path=str(root/'workbench-registration.png'))
        assert not errors, errors
        browser.close()
    with httpx.Client(base_url='http://127.0.0.1:8000', trust_env=False) as client:
        for key in ('network', 'registration'):
            response = client.get('/spatial/artifacts/'+imported[key]['id'])
            response.raise_for_status()
            assert response.json()['review'] is None
    (root/'browser-validation.json').write_text(json.dumps({'page_errors': errors,
        'road_map_points': 27, 'scan_correspondences': 80, 'live_reviews': None,
        'widths': [320, 768, 1024, 1440]}), encoding='utf8')
    print('PASS: real-source live datasets, local XYZ, pending review, responsive UI; no live approvals.')


if __name__ == '__main__':
    main()
