"""Explicit synthetic fixtures for isolated browser regressions, never served by frontend/."""
from pathlib import Path


def fixture(page):
    source = (Path(__file__).parent / 'fixtures/workbench.js').read_text(encoding='utf-8')
    return page.evaluate('() => {' + source.replace('export function', 'function') + '; return makeDemo();}')


def load_ui_fixture(page):
    page.locator('.workspace-stage').wait_for(state='attached')
    page.evaluate("""async data => {
        const {state, resetSelection} = await import('./state.js');
        Object.assign(state, data);
        resetSelection();
        state.showTimeline = true;
        window.dispatchEvent(new Event('hashchange'));
    }""", fixture(page))
