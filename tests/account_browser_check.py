"""Run against the disposable examples.frontend_test_server on port 8002."""
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='chrome')
        errors = []
        def new_page():
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto('http://127.0.0.1:8080/#login')
            page.wait_for_load_state('networkidle')
            return page

        def fields(page, form_id, user, password):
            form = page.locator('#' + form_id)
            form.locator('[name=user_id]').fill(user)
            form.locator('[name=password]').fill(password)
            form.locator('details').evaluate('(e) => e.open = true')
            form.locator('[name=workspace]').fill('browser-test')
            form.locator('[name=base]').fill('http://127.0.0.1:8002')
            return form

        def login(page, user, password):
            fields(page, 'login-form', user, password).get_by_role('button', name='登录工作台').click()
            expect(page.locator('.topbar')).to_contain_text('后端已连接', timeout=15000)

        def settings(page):
            page.get_by_role('button', name='连接设置', exact=True).click()
            page.get_by_role('button', name='账号管理', exact=True).click()

        user, password = 'browser-' + uuid4().hex[:10], 'browser-account-password'
        member, admin = new_page(), new_page()
        member.get_by_role('button', name='注册', exact=True).click()
        form = fields(member, 'register-account-form', user, password)
        form.locator('[name=confirm_password]').fill(password)
        form.get_by_role('button', name='提交注册申请').click()
        expect(member.locator('.ds-terms[role=status]')).to_contain_text('申请已提交')
        login(admin, 'admin', 'frontend-test-password')
        settings(admin)
        admin.get_by_role('button', name='成员与注册审批').click()
        row = admin.locator('.member-form').filter(has=admin.locator('[name=user_id][value="' + user + '"]'))
        row.get_by_role('button', name='批准', exact=True).click()
        expect(row).to_contain_text('已启用')
        login(member, user, password)
        settings(member)
        expect(member.get_by_role('button', name='成员与注册审批')).to_have_count(0)
        form = member.locator('#change-password-form')
        form.locator('[name=current_password]').fill(password)
        form.locator('[name=password]').fill(password + '-new')
        form.locator('[name=confirm_password]').fill(password + '-new')
        form.get_by_role('button', name='修改密码', exact=True).click()
        expect(member.locator('.ds-terms[role=status]')).to_contain_text('密码已修改')
        member.close()
        member = new_page()
        login(member, user, password + '-new')
        row.get_by_role('button', name='签发重置码').click()
        code = admin.locator('#dialog input[readonly]').input_value()
        member.close()
        member = new_page()
        member.get_by_role('button', name='忘记密码？').click()
        form = fields(member, 'reset-password-form', user, password)
        form.locator('[name=confirm_password]').fill(password)
        form.locator('[name=reset_code]').fill(code)
        form.get_by_role('button', name='重置密码', exact=True).click()
        expect(member.locator('.ds-terms[role=status]')).to_contain_text('密码已重置')
        login(member, user, password)
        assert not errors, errors
        browser.close()
        print('PASS: registration, approval, login, role visibility, password change and recovery.')


if __name__ == '__main__':
    main()
