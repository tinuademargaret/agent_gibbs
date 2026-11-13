from dataclasses import dataclass, field
from uuid import uuid4

@dataclass
class ReviewSession:
    queue: list[tuple[int, bool]]
    position: int = 0
    revealed: bool = False
    rated: bool = False
    knew: int = 0
    missed: int = 0
    token: str = field(default_factory=lambda: str(uuid4()))

    @property
    def done(self):
        return self.position >= len(self.queue)

    def record(self, rating):
        if not self.revealed or self.rated:
            raise ValueError('Reveal the card before rating it once.')
        card_id, retry = self.queue[self.position]
        if rating == 'missed':
            self.missed += 1
            if not retry:
                self.queue.append((card_id, True))
        else:
            self.knew += 1
        self.rated = True

    def advance(self):
        if not self.rated:
            raise ValueError('Rate this card before continuing.')
        self.position += 1
        self.revealed = self.rated = False
        self.token = str(uuid4())
