from ortools.sat.python import cp_model

from .models import Scenario


def compare(scenario: Scenario) -> list[dict]:
    plans = []
    # ponytail: one concurrent wave; sequencing and team-specific routes need a later scheduling model.
    for strategy in ('urgency', 'coverage', 'lower_risk'):
        model = cp_model.CpModel()
        pairs = {}
        excluded = {}
        for site in scenario.sites:
            reasons = []
            if not site.accessible:
                reasons.append('道路不可达')
            if site.risk > scenario.max_risk:
                reasons.append('超过允许风险等级')
            if site.travel_minutes + site.work_minutes > scenario.horizon_minutes:
                reasons.append('无法在本轮时间窗口内完成')
            if not any(site.required_skills <= team.skills for team in scenario.teams):
                reasons.append('没有具备所需技能的队伍')
            if any(n > scenario.equipment.get(k, 0) for k, n in site.equipment.items()):
                reasons.append('所需装备不足')
            if reasons:
                excluded[site.id] = reasons
                continue
            for team in scenario.teams:
                if site.required_skills <= team.skills:
                    pairs[team.id, site.id] = model.new_bool_var(f'{team.id}:{site.id}')
        for team in scenario.teams:
            model.add(sum(v for (t, s), v in pairs.items() if t == team.id) <= 1)
        for site in scenario.sites:
            model.add(sum(v for (t, s), v in pairs.items() if s == site.id) <= 1)
        for equipment in {key for s in scenario.sites for key in s.equipment}:
            model.add(sum(v * site.equipment.get(equipment, 0)
                          for site in scenario.sites
                          for (t, s), v in pairs.items() if s == site.id)
                      <= scenario.equipment.get(equipment, 0))
        scores = {}
        for site in scenario.sites:
            scores[site.id] = {
                'urgency': site.people * site.urgency,
                'coverage': site.people,
                'lower_risk': site.people * (6 - site.risk),
            }[strategy]
        model.maximize(sum(v * scores[s] for (t, s), v in pairs.items()))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 3
        solver.parameters.num_search_workers = 1
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(f'Planner did not find a solution: {solver.status_name(status)}')
        selected = [(t, s) for (t, s), v in pairs.items() if solver.value(v)]
        by_id = {s.id: s for s in scenario.sites}
        assigned = {s for t, s in selected}
        plans.append({
            'strategy': strategy, 'solver_status': solver.status_name(status),
            'objective_value': solver.objective_value,
            'objective_formula': {'urgency': 'sum(people * urgency)', 'coverage': 'sum(people)',
                                  'lower_risk': 'sum(people * (6 - risk))'}[strategy],
            'assignments': [{'team_id': t, 'site_id': s, 'evidence_ids': by_id[s].evidence_ids,
                             'reason': f'技能满足，路线可达，风险和时间符合本轮约束；目标贡献 {scores[s]}'}
                            for t, s in selected],
            'people_covered': sum(by_id[s].people for s in assigned),
            'total_risk_score': sum(by_id[s].risk for s in assigned),
            'unassigned': {s.id: excluded.get(s.id, ['本轮资源竞争或目标函数取舍'])
                           for s in scenario.sites if s.id not in assigned},
            'assumptions': ['单轮并行分配，每队最多一个救援点，每点最多一队',
                            '通行、时间、人数与风险均以输入快照为准，未作现场独立核验',
                            '覆盖人数不代表成功获救人数；评分不是医学分诊或生存概率',
                            '三种策略可能得到相同方案；风险偏好采用加权得分，不保证总风险最小'],
            'requires_human_approval': True,
        })
    return plans
