"""Escolhe um esforço para um modelo fixo usando o checkpoint público do Laya."""

import sys
import laya
from scripts.laya_device import detect_device

model = 'gpt-6.1-sol'
task = ' '.join(sys.argv[1:]) or 'Fix a typo in README.md.'
agent = laya.load('convaiinnovations/laya', device=detect_device())
result = agent.predict(
    task,
    {
        'effort': {
            'type': 'choice',
            'instructions': f'Choose the lowest reasoning effort for {model} that should complete this task correctly.',
            'criteria': {
                'low': 'small mechanical change following an existing pattern',
                'medium': 'day-to-day work with a clear scope',
                'high': 'work needing careful verification and edge-case reasoning',
            },
        },
    },
)
answer = result['answers']['effort']
print(f"Dispositivo: {agent.device} | modelo: {model} | effort sugerido: {answer['choice']}")
