"""Real WebGL/worker and attribution sanitization check; requires frontend on 8080."""
from playwright.sync_api import expect, sync_playwright


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel='chrome')
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors, workers = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('worker', lambda worker: workers.append(worker.url))
    page.goto('http://127.0.0.1:8080/#command')
    page.wait_for_load_state('networkidle')
    expect(page.locator('.maplibregl-canvas')).to_be_visible()
    expect(page.locator('.geo-label')).not_to_have_count(0)
    page.evaluate('''async () => {
        const gl = await import('./vendor/maplibre-gl.mjs');
        const container = document.createElement('div');
        container.id = 'vendor-audit';
        container.style.cssText = 'position:fixed;inset:0;width:500px;height:500px;z-index:99999';
        document.body.append(container);
        window.__auditXss = false;
        const map = window.__auditMap = new gl.Map({
            container, center:[0,0], zoom:4, attributionControl:false,
            style:{version:8,sources:{},layers:[]}
        });
        window.__auditMapErrors = [];
        map.on('error', e => window.__auditMapErrors.push(e.error.message));
        map.addControl(new gl.AttributionControl({compact:false, customAttribution:
            '<img src="data:," onerror="window.__auditXss=true" onload="window.__auditXss=true">' +
            '<a href="javascript:window.__auditXss=true" onclick="window.__auditXss=true" onmouseover="window.__auditXss=true">audit</a>'
        }));
        await new Promise(resolve => map.on('load', resolve));
        map.addSource('audit', {type:'geojson', data:{type:'FeatureCollection',features:[
            {type:'Feature',geometry:{type:'Point',coordinates:[0,0]},properties:{id:'audit'}}
        ]}});
        map.addLayer({id:'audit',type:'circle',source:'audit',paint:{'circle-radius':8}});
    }''')
    page.wait_for_function("window.__auditMap.queryRenderedFeatures({layers:['audit']}).length > 0")
    assert page.evaluate('''() => {
        const nodes = document.querySelectorAll('#vendor-audit .maplibregl-ctrl-attrib *');
        return !window.__auditXss && [...nodes].every(el => [...el.attributes].every(a =>
            !a.name.toLowerCase().startsWith('on') && !/^javascript:/i.test(a.value.trim())));
    }'''), 'Unsafe attribution survived sanitization'
    assert any('maplibre-gl-worker.mjs' in url for url in workers), workers
    assert page.evaluate('window.__auditMapErrors') == []
    assert errors == [], errors
    page.evaluate('window.__auditMap.remove()')
    browser.close()
print('PASS: WebGL map, GeoJSON worker rendering and attribution XSS regression.')
