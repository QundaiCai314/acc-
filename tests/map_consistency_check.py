"""Read-only browser checks using explicit, isolated UI fixtures."""
from playwright.sync_api import sync_playwright
from ui_fixture import load_ui_fixture


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel='chrome')
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.goto('http://127.0.0.1:8080/#command')
    page.wait_for_load_state('networkidle')
    load_ui_fixture(page)
    result = page.evaluate('''async () => {
        const {state} = await import('./state.js');
        const {mapData} = await import('./gis.js');
        const {mapSvg} = await import('./map.js');
        const {command} = await import('./workbench.js');
        state.showIntel = true;
        const exerciseLabel = command().includes('来源标记：演练') && !command().includes('来源标记：实测');
        const network = state.artifacts.find(a => a.artifact_type === 'road_network');
        const other = structuredClone(network);
        other.id = 'second-network';
        other.snapshot.edges = [
            {...other.snapshot.edges[0], modes:['vehicle']},
            {...other.snapshot.edges[1], id:'second-only', modes:['vehicle']}
        ];
        state.artifacts.push(other);
        state.route = {network:{artifact_id:other.id}, query:{as_of:state.asOf},
                       edges:[other.snapshot.edges[0]]};
        const selected = mapData().roads.features.map(f => f.properties);
        const svgUsesSelected = mapSvg().includes('仅车辆');
        state.route = null;
        const edge = network.snapshot.edges[0];
        edge.annotation_ids = ['ann-east'];
        const status = () => mapData().roads.features.find(f => f.properties.id === edge.id).properties.status;
        const blocked = status();
        const svg = new DOMParser().parseFromString(mapSvg(), 'image/svg+xml');
        const svgBlockedStroke = svg.querySelector('polyline').getAttribute('stroke');
        state.annotations.find(a => a.id === 'ann-east').status = 'withdrawn';
        const withdrawn = status();
        edge.annotation_ids = ['missing-evidence'];
        const missing = status();
        edge.annotation_ids = [];
        const independent = status();
        edge.annotation_ids = ['ann-east'];
        const ann = state.annotations.find(a => a.id === 'ann-east');
        const image = state.images.find(i => i.id === ann.image_id);
        ann.status = 'approved';
        const base = Date.parse(state.asOf), iso = h => new Date(base + h * 3600000).toISOString();
        image.captured_at = iso(1);
        const future = status();
        image.captured_at = iso(-30);
        const oldBrowse = status();
        state.route = {network:{artifact_id:network.id}, query:{as_of:state.asOf}, edges:[]};
        const oldRoute = status();
        state.route = null;
        image.captured_at = null;
        image.captured_on = state.asOf.slice(0, 10);
        const partialDay = status();
        image.captured_on = iso(-72).slice(0, 10);
        state.hours = 168;
        const wholeDay = status();
        ann.review.approved_annotation = {...ann.annotation, observation:'no_obstacle_visible'};
        const corrected = status();
        state.route = {network:{artifact_id:other.id}, query:{as_of:state.asOf}, edges:other.snapshot.edges};
        other.snapshot.valid_until = iso(-1);
        const expiredNetwork = mapData().roads.features.length;
        other.snapshot.valid_until = iso(24);
        other.status = 'pending_review';
        const pendingNetwork = mapData().roads.features.length;
        other.status = 'withdrawn';
        const withdrawnNetwork = mapData().roads.features.length;
        return {exerciseLabel, selected, svgUsesSelected, blocked, svgBlockedStroke, withdrawn, missing, independent,
                future, oldBrowse, oldRoute, partialDay, wholeDay, corrected,
                expiredNetwork, pendingNetwork, withdrawnNetwork};
    }''')
    assert [r['id'] for r in result['selected']] == ['r1', 'second-only'], result
    assert result['exerciseLabel'], result
    assert result['selected'][0]['route'] is True, result
    assert result['selected'][1]['route'] is False, result
    assert result['selected'][0]['label'] == '仅车辆', result
    assert result['svgUsesSelected'] and result['svgBlockedStroke'] == '#f18d7c', result
    assert result['blocked'] == 'blocked', result
    assert result['withdrawn'] == result['missing'] == 'unknown', result
    assert result['independent'] == 'open', result
    assert result['future'] == result['oldBrowse'] == result['partialDay'] == 'unknown', result
    assert result['oldRoute'] == result['wholeDay'] == 'blocked', result
    assert result['corrected'] == 'open', result
    assert result['withdrawnNetwork'] == result['pendingNetwork'] == result['expiredNetwork'] == 0, result
    browser.close()
print('PASS: exact route snapshot, evidence-aware road status, withdrawn evidence/network, vehicle-only labels and SVG fallback.')
