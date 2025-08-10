# CREATIVE Mode - Design and Architecture Phase

## Цель режима
CREATIVE Mode предназначен для детального проектирования компонентов, идентифицированных во время PLAN Mode как требующие creative phase. Фокус на архитектурном дизайне, алгоритмическом проектировании и UI/UX дизайне.

## Входные условия
- PLAN Mode завершен с идентифицированными Creative Phase компонентами
- Требования и ограничения определены
- Memory Bank содержит architectural context и planning artifacts

## Типы Creative Phase

### 🏗️ Architecture Design
**Применяется когда:**
- Требуется проектирование новых архитектурных паттернов
- Необходимы system design решения
- Нужны integration patterns и data flow designs

**Процесс:**
1. Analysis требований и ограничений
2. Generation multiple architectural options
3. Evaluation pros/cons каждого варианта
4. Selection и justification recommended approach
5. Detailed design с диаграммами
6. Implementation guidelines

### ⚙️ Algorithm Design  
**Применяется когда:**
- Требуются сложные алгоритмы или data structures
- Нужна оптимизация performance-critical компонентов
- Необходимо решение computational problems

**Процесс:**
1. Problem definition и constraints
2. Algorithm alternatives generation
3. Complexity analysis (time/space)
4. Edge cases identification
5. Algorithm selection и optimization
6. Implementation strategy

### �� UI/UX Design
**Применяется когда:**
- Проектирование пользовательских интерфейсов
- Создание user experience flows
- Design системы interaction patterns

**Процесс:**
1. User requirements analysis
2. Interface mockups generation
3. UX flow design
4. Accessibility considerations
5. Design system integration
6. Implementation specifications

## Общий Creative Phase Workflow

### Phase Entry: 🎨🎨�� ENTERING CREATIVE PHASE
```markdown
# Creative Phase: [Component Name] - [Type: Architecture/Algorithm/UI-UX]

## Component Description
[What is this component? What does it do?]

## Requirements & Constraints
[What must this component satisfy?]
```

### Design Process Steps

#### Step 1: Requirements Analysis
- Функциональные требования
- Нефункциональные требования (performance, scalability, security)
- Technical constraints
- Integration requirements
- Business constraints

#### Step 2: Options Generation
**Минимум 2-4 различных подхода:**
- Option A: [Description and approach]
- Option B: [Alternative approach]  
- Option C: [Another alternative]
- Option D: [Creative/innovative approach]

#### Step 3: Options Analysis
**Для каждого варианта:**
- **Pros**: Преимущества подхода
- **Cons**: Недостатки и ограничения
- **Complexity**: Implementation complexity
- **Performance**: Expected performance characteristics
- **Maintainability**: Long-term maintenance considerations
- **Scalability**: Growth и scaling potential

#### Step 4: Evaluation Matrix
```markdown
| Criteria | Weight | Option A | Option B | Option C | Option D |
|----------|--------|----------|----------|----------|----------|
| Performance | 30% | 8/10 | 6/10 | 9/10 | 7/10 |
| Complexity | 25% | 6/10 | 9/10 | 4/10 | 5/10 |
| Scalability | 20% | 7/10 | 8/10 | 9/10 | 8/10 |
| Maintainability | 15% | 8/10 | 7/10 | 6/10 | 9/10 |
| Innovation | 10% | 5/10 | 6/10 | 7/10 | 9/10 |
| **Total** | 100% | **X.X** | **Y.Y** | **Z.Z** | **W.W** |
```

#### Step 5: Recommended Approach
- **Selected Option**: [Выбранный вариант]
- **Justification**: [Почему именно этот вариант]
- **Trade-offs**: [Какие компромиссы приняты]
- **Risk Mitigation**: [Как минимизированы риски]

#### Step 6: Detailed Design
- **Architecture Diagrams** (для Architecture Design)
- **Algorithm Specifications** (для Algorithm Design)  
- **UI Mockups/Wireframes** (для UI/UX Design)
- **API Interfaces** и contracts
- **Data Structures** и schemas
- **State Machines** и workflows

#### Step 7: Implementation Guidelines
- **Development approach** и best practices
- **Testing strategy** specific для компонента
- **Performance considerations** и optimization points
- **Security guidelines** если применимо
- **Documentation requirements**

#### Step 8: Verification Checkpoint
- **Requirements Coverage**: Все ли требования покрыты?
- **Design Consistency**: Соответствует ли дизайн общей архитектуре?
- **Implementation Feasibility**: Реализуем ли дизайн с current tech stack?
- **Performance Expectations**: Достижимы ли performance targets?
- **Risk Assessment**: Приемлемы ли identified risks?

### Phase Exit: 🎨🎨🎨 EXITING CREATIVE PHASE

```markdown
## Final Design Summary
[Brief summary of selected design]

## Implementation Readiness
- [ ] Design fully specified
- [ ] Implementation guidelines clear
- [ ] Dependencies identified
- [ ] Risks documented and mitigated
- [ ] Ready for IMPLEMENT Mode

## Artifacts Created
- [List of design documents, diagrams, specifications]
```

## Критерии завершения Creative Phase

### Для Architecture Design:
- [ ] Multiple architectural options explored
- [ ] Selected architecture fully documented
- [ ] Integration points clearly defined
- [ ] Performance characteristics estimated
- [ ] Implementation guidelines provided

### Для Algorithm Design:
- [ ] Algorithm complexity analyzed
- [ ] Edge cases identified и handled
- [ ] Performance optimizations considered
- [ ] Alternative algorithms evaluated
- [ ] Implementation strategy defined

### Для UI/UX Design:
- [ ] User flows documented
- [ ] Interface mockups created
- [ ] Accessibility requirements addressed
- [ ] Design system compliance verified
- [ ] Implementation specifications provided

## Переходы

- **При завершении всех Creative Phase компонентов** → IMPLEMENT Mode
- **При обнаружении missing requirements** → PLAN Mode (дополнительное планирование)
- **При fundamental changes в requirements** → VAN Mode (переанализ)

## Templates & Examples

### Architecture Design Template
```markdown
# Architecture Design: [Component Name]

## Requirements & Constraints
[Detailed requirements]

## Architecture Options

### Option A: [Name]
**Approach**: [Description]
**Pros**: [Advantages]
**Cons**: [Disadvantages]
**Complexity**: [Assessment]

### Option B: [Name]
[Similar structure]

## Evaluation & Selection
[Evaluation matrix и justification]

## Detailed Architecture
[Diagrams, specifications, interfaces]

## Implementation Guidelines
[Development approach, testing, performance]
```

### Algorithm Design Template  
```markdown
# Algorithm Design: [Component Name]

## Problem Definition
[What problem are we solving?]

## Algorithm Options

### Option A: [Algorithm Name]
**Approach**: [High-level description]
**Time Complexity**: O(?)
**Space Complexity**: O(?)
**Pros**: [Advantages]
**Cons**: [Disadvantages]

[Repeat for other options]

## Selected Algorithm
[Choice и justification]

## Implementation Strategy
[Detailed approach, data structures, edge cases]
```
