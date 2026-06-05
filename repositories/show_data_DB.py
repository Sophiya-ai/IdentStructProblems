import json
import logging
import os
import re
from typing import List, Dict, Any
from db import get_connection, put_connection
from repositories.hierarchy_repo import get_full_hierarchy
from repositories.subproblems_repo import get_root_problems, get_all_problems_light
from repositories.hierarchy_by_root import get_hierarchy_for_root, get_hierarchy_by_macro_id
from repositories.hierarchy_recursive import get_hierarchy_for_root_recursive, get_hierarchy_by_macro_id_recursive
from display_hierarchy import show as display_hierarchy
from call_llm import call_openrouter
from prompts import PROMPT_SIMILARITY_CHECK
from micro_model import parse_micro_model as parse_json


logger = logging.getLogger(__name__)

DEFAULT_JUDGE_MODEL = os.getenv("DEFAULT_JUDGE_MODEL")


def full_hierarchy():
    """Показать полную иерархию из БД."""
    hierarchy = get_full_hierarchy()
    display_hierarchy(hierarchy, save_json=True)  # выведет в консоль и сохранит в JSON


def list_roots():
    """Вывод всех корневых проблем."""
    roots = get_root_problems()
    if not roots:
        print("Корневые проблемы отсутствуют.")
        return

    # Заголовок таблицы – печатается заголовок с тремя колонками, разделёнными пробелами
    print("\n=== Список корневых проблем ===")
    print(f"{'db_id':<6} {'macro_id':<12} {'sbj (субъект)':<20}")
    # Например, строка 'db_id' выравнивается влево в поле шириной 6 символов (знак <).
    # Если название короче, остальное место заполняется пробелами справа
    print("-" * 45)
    for r in roots:
        sbj = r['macro_model'].get('sbj', '?') if r['macro_model'] else '?'
        print(f"{r['id']:<6} {r['macro_id']:<12} {sbj:<20}")


def show_hierarchy_by_db_id():
    """Запрашивает db_id и выводит иерархию."""
    raw = input("Введите db_id корневой проблемы (число): ").strip()
    if not raw.isdigit():
        print("Ошибка: db_id должен быть целым числом.")
        return
    db_id = int(raw)
    hierarchy = get_hierarchy_for_root(db_id)
    if hierarchy is None:
        print(f"Проблема с db_id={db_id} не найдена.")
        return
    print(f"\n=== Иерархия для корневой проблемы db_id={db_id} ===")
    display_hierarchy([hierarchy], save_json=False)


def show_hierarchy_by_macro_id():
    """Запрашивает макромодельный идентификатор и выводит иерархию."""
    macro_id = input("Введите макромодельный идентификатор (например, P1): ").strip()
    if not macro_id:
        print("Ошибка: идентификатор не может быть пустым.")
        return
    hierarchy = get_hierarchy_by_macro_id(macro_id)
    if hierarchy is None:
        print(f"Корневая проблема с macro_id='{macro_id}' не найдена.")
        return
    print(f"\n=== Иерархия для корневой проблемы macro_id='{macro_id}' ===")
    display_hierarchy([hierarchy], save_json=False)


def show_hierarchy_recursive_by_db_id():
    raw = input("Введите db_id корневой проблемы (число): ").strip()
    if not raw.isdigit():
        print("Ошибка: db_id должен быть целым числом.")
        return
    db_id = int(raw)
    hierarchy = get_hierarchy_for_root_recursive(db_id)
    if hierarchy is None:
        print(f"Проблема с db_id={db_id} не найдена.")
        return
    print(f"\n=== Иерархия (рекурсивный CTE) для корневой проблемы db_id={db_id} ===")
    display_hierarchy([hierarchy], save_json=False)


def show_hierarchy_recursive_by_macro_id():
    macro_id = input("Введите макромодельный идентификатор (например, P1): ").strip()
    if not macro_id:
        print("Ошибка: идентификатор не может быть пустым.")
        return
    hierarchy = get_hierarchy_by_macro_id_recursive(macro_id)
    if hierarchy is None:
        print(f"Корневая проблема с macro_id='{macro_id}' не найдена.")
        return
    print(f"\n=== Иерархия (рекурсивный CTE) для корневой проблемы macro_id='{macro_id}' ===")
    display_hierarchy([hierarchy], save_json=False)



def load_problems_lowconfident(root_db_id: int = None, filepath: str = "low_confidence_problems.json") -> list[dict]:
    """
    Выбирает из БД подпроблемы с низкой уверенностью верификации (confidence_micro = 'low' ИЛИ confidence_macro = 'low').
    Если root_db_id задан, только в поддереве этой корневой проблемы (включая её саму).
    Если не задан — по всей БД.

    - Выводит их на консоль в удобочитаемом формате.
    - Сохраняет в JSON‑файл.
    - Возвращает список найденных записей (словарей).
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if root_db_id is not None:
                # Рекурсивный CTE для получения всех id поддерева
                cur.execute(
                    """
                    WITH RECURSIVE subtree AS (
                        SELECT id FROM subproblems WHERE id = %s
                        UNION ALL
                        SELECT s.id FROM subproblems s
                        INNER JOIN subtree ON s.parent_id = subtree.id
                    )
                    SELECT s."id", s."parent_id", s."macro_model", s."micro_model",
                           s."confidence_macro", s."reasoning_macro",
                           s."confidence_micro", s."reasoning_micro"
                    FROM subproblems s
                    WHERE s.id IN (SELECT id FROM subtree)
                      AND (s."confidence_micro" = 'low' OR s."confidence_macro" = 'low')
                    ORDER BY s."id";
                    """,
                    (root_db_id,)
                )
            else:
                cur.execute(
                    """
                    SELECT "id", "parent_id", "macro_model", "micro_model",
                           "confidence_macro", "reasoning_macro",
                           "confidence_micro", "reasoning_micro"
                    FROM "subproblems"
                    WHERE "confidence_micro" = 'low' OR "confidence_macro" = 'low'
                    ORDER BY "id";
                    """
                )
            rows = cur.fetchall()
            problems = []
            for r in rows:
                problems.append({
                    "id": r[0],
                    "parent_id": r[1],
                    "macro_model": r[2],
                    "micro_model": r[3],
                    "confidence_macro": r[4],
                    "reasoning_macro": r[5],
                    "confidence_micro": r[6],
                    "reasoning_micro": r[7],
                })
    finally:
        put_connection(conn)

    # Вывод на консоль
    if not problems:
        print("Проблем с низкой уверенностью не найдено.")
    else:
        print(f"Найдено {len(problems)} проблем(ы) с низкой уверенностью:\n")
        for p in problems:
            print(f"ID: {p['id']}")
            print(f"Родительский ID: {p['parent_id']}")
            print(f"Макромодель: {json.dumps(p['macro_model'], ensure_ascii=False, indent=2)}")
            print(f"Микромодель: {json.dumps(p['micro_model'], ensure_ascii=False, indent=2)}")
            print(f"Confidence macro: {p['confidence_macro']}")
            print(f"Reasoning macro: {p['reasoning_macro']}")
            print(f"Confidence micro: {p['confidence_micro']}")
            print(f"Reasoning micro: {p['reasoning_micro']}")
            print("-" * 60)

    # Сохранение в файл
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(problems, f, ensure_ascii=False, indent=2)
    print(f"Данные сохранены в файл: {os.path.abspath(filepath)}")

    return problems


def _prefilter_candidates(new_macro_id: str, all_problems: List[dict], min_word_length: int = 3) -> List[dict]:
    """
    Быстрый предварительный отбор: возвращает проблемы, в macro_model->>'id' которых
    встречаются ВСЕ значимые слова из new_macro_id.
    Стоп-слова и короткие слова игнорируются.
    """
    stop_words = {
        'для','и','в','на','по','с','к','у','о','от','из','при','за','не',
        'как','что','это','а','но','или','так','то','же','бы','все','под','над',
        'без','до','об','во','со','из-за','из-под'
    }
    words = re.findall(r'[а-яёa-z]+', new_macro_id.lower())
    significant = [w for w in words if len(w) >= min_word_length and w not in stop_words]
    if not significant:
        significant = words[:3] if words else [new_macro_id.lower().strip()]

    candidates = []
    for p in all_problems:
        mm = p.get("macro_model") or {}
        macro_id = mm.get("id", "")
        if all(word in macro_id.lower() for word in significant):
            candidates.append(p)
    return candidates


def similarity_problems(new_macro: dict, max_candidates: int = 30) -> Dict[str, Any]:
    """
    Проверяет дубликаты новой проблемы среди всех проблем в БД.
    Использует предварительный отбор по ключевым словам, затем модель‑судью.
    Если кандидатов больше max_candidates, обрезает список, предупреждая в лог.

    Возвращает:
    {
        "similar": [ <полные объекты проблем> ],
        "confidence_new": float,
        "reasoning": str
    }
    """
    # 1. Все проблемы из БД
    all_problems = get_all_problems_light()
    if not all_problems:
        return {"similar": [], "confidence_new": 1.0, "reasoning": "База пуста"}

    # 2. Предварительный отбор
    new_macro_id = new_macro.get("id", "")
    candidates = _prefilter_candidates(new_macro_id, all_problems)

    if not candidates:
        return {"similar": [], "confidence_new": 1.0, "reasoning": "Не найдено кандидатов по ключевым словам"}

    if len(candidates) > max_candidates:
        logger.warning(f"Слишком много кандидатов ({len(candidates)}), оставляем первые {max_candidates}")
        candidates = candidates[:max_candidates]

    # 3. Подготовка данных для судьи
    existing_list = []
    for p in candidates:
        mm = p.get("macro_model", {})
        existing_list.append({
            "db_id": p["id"],
            "parent_id": p["parent_id"],
            "macro_id": mm.get("id", ""),
            "sit": mm.get("sit", ""),
            "sbj": mm.get("sbj", ""),
        })

    new_macro_json = json.dumps(new_macro, ensure_ascii=False, indent=2)
    existing_json = json.dumps(existing_list, ensure_ascii=False, indent=2)

    prompt = PROMPT_SIMILARITY_CHECK.format(
        new_macro_json=new_macro_json,
        existing_problems_json=existing_json
    )

    raw = call_openrouter(prompt, model=DEFAULT_JUDGE_MODEL, temperature=0.1)
    result = parse_json(raw)

    similar_indices = result.get("similar", [])
    confidence_new = result.get("confidence_new", 1.0)
    reasoning = result.get("reasoning", "")

    # Преобразуем индексы обратно в полные объекты проблем
    similar_problems = []
    for idx in similar_indices:
        if isinstance(idx, int) and 0 <= idx < len(candidates):
            similar_problems.append(candidates[idx])

    return {
        "similar": similar_problems,
        "confidence_new": confidence_new,
        "reasoning": reasoning
    }