"""A arquitetura que o CLAUDE.md descreve, conferida pelo codigo (so le os
arquivos, com `ast`: nao importa o app).

- **Camadas**: config <- db <- validators/money/dates/auth/... <- services <-
  routes <- app. Um modulo da raiz nunca importa `services` nem `routes`; um
  servico nunca importa `routes`; um blueprint nunca importa outro; nada
  importa `app`.
- **Sem ciclos**, nem pelos imports feitos dentro de funcao: um ciclo assim so
  aparece quando alguem sobe o import para o topo do arquivo, e ai o app nao
  sobe.
- **Catraca dos privados**: usar o `_nome` de outro modulo (`inbox._cents`)
  fura a fronteira dele. Os usos de hoje estao em
  `tests/architecture_private_uses.txt`; um uso novo falha, e um uso que saiu
  tem que sair da lista (ela so diminui). Para tirar um: de um nome publico a
  funcao no modulo dela, ou mova-a para onde e usada.
"""

import ast
import os

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "architecture_private_uses.txt")
SKIPPED_DIRS = {"tests", "scripts", "__pycache__", "backups", "attachments", "logs"}


def app_modules():
    """{nome.do.modulo: caminho} de tudo o que o app importa (sem testes nem scripts)."""
    found = {}
    for folder, dirs, files in os.walk(BACKEND):
        dirs[:] = [name for name in dirs if name not in SKIPPED_DIRS and not name.startswith(".")]
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(folder, name)
                module = os.path.relpath(path, BACKEND)[:-3].replace(os.sep, ".")
                found[module] = path
    return found


MODULES = app_modules()
TREES = {}
for _module, _path in MODULES.items():
    with open(_path, encoding="utf-8") as _file:
        TREES[_module] = ast.parse(_file.read())


def imports_of(module):
    """[(modulo importado, nome local ou None)] de todos os imports do arquivo,
    os de dentro de funcao tambem."""
    found = []
    package = module.rsplit(".", 1)[0] if "." in module else ""
    for node in ast.walk(TREES[module]):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in MODULES:
                    found.append((alias.name, alias.asname or alias.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = ".".join(part for part in (package, base) if part)
            for alias in node.names:
                full = f"{base}.{alias.name}" if base else alias.name
                if full in MODULES:  # from services import inbox
                    found.append((full, alias.asname or alias.name))
                elif base in MODULES:  # from services.inbox import normalized
                    found.append((base, None))
    return found


GRAPH = {module: sorted({target for target, _name in imports_of(module) if target != module}) for module in MODULES}


def layer(module):
    if module == "app":
        return 3
    if module.startswith("routes"):
        return 2
    if module.startswith("services"):
        return 1
    return 0


def test_the_layers_only_point_down():
    broken = []
    for module, targets in GRAPH.items():
        for target in targets:
            if layer(target) > layer(module):
                broken.append(f"{module} importa {target}")
            if module.startswith("routes.") and target.startswith("routes."):
                broken.append(f"{module} importa outro blueprint, {target}")
            if target == "app":
                broken.append(f"{module} importa app")
    assert broken == []


def cycles(graph):
    """Componentes fortemente conexos com mais de um modulo (Tarjan, iterativo)."""
    index, low, on_stack, stack, found, counter = {}, {}, set(), [], [], [0]
    for root in sorted(graph):
        if root in index:
            continue
        work = [(root, iter(graph[root]))]
        index[root] = low[root] = counter[0]
        counter[0] += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, targets = work[-1]
            advanced = False
            for target in targets:
                if target not in index:
                    index[target] = low[target] = counter[0]
                    counter[0] += 1
                    stack.append(target)
                    on_stack.add(target)
                    work.append((target, iter(graph[target])))
                    advanced = True
                    break
                if target in on_stack:
                    low[node] = min(low[node], index[target])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    found.append(sorted(component))
    return found


def test_no_import_cycle_even_through_function_level_imports():
    assert cycles(GRAPH) == []


def test_the_cycle_finder_finds_one():
    assert cycles({"a": ["b"], "b": ["c"], "c": ["a"], "d": ["a"]}) == [["a", "b", "c"]]


def private_uses():
    """{"arquivo: modulo._nome"}: cada `_privado` de outro modulo do app que um arquivo usa."""
    found = set()
    for module in MODULES:
        aliases = {name: target for target, name in imports_of(module) if name and target != module}
        path = os.path.relpath(MODULES[module], BACKEND).replace(os.sep, "/")
        for node in ast.walk(TREES[module]):
            if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
                continue
            name = node.attr
            if not name.startswith("_") or name.startswith("__"):
                continue
            target = aliases.get(node.value.id)
            if target:
                found.add(f"{path}: {target}.{name}")
    return found


def allowed_private_uses():
    with open(ALLOWED, encoding="utf-8") as file:
        return {line.strip() for line in file if line.strip() and not line.startswith("#")}


def test_no_new_use_of_another_modules_private_name():
    new = sorted(private_uses() - allowed_private_uses())
    assert new == [], "use um nome publico, ou mova a funcao: " + "; ".join(new)


def test_the_allowed_list_only_shrinks():
    gone = sorted(allowed_private_uses() - private_uses())
    assert gone == [], "ja nao existem: tire de tests/architecture_private_uses.txt: " + "; ".join(gone)
