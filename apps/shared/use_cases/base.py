import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseUseCase(ABC):
    """
    Base para todos os use cases do projeto. `execute()` é o único método
    público — ele loga início, execução e fim, e delega o trabalho de
    verdade para `perform_request()`, que toda subclasse é obrigada a
    implementar.
    """

    def execute(self, *args, **kwargs):
        logger.info("[%s] iniciando", self.__class__.__name__)
        try:
            result = self.perform_request(*args, **kwargs)
        except Exception:
            logger.exception("[%s] falhou durante a execução", self.__class__.__name__)
            raise
        else:
            logger.info("[%s] executado com sucesso", self.__class__.__name__)
            return result
        finally:
            logger.info("[%s] finalizado", self.__class__.__name__)

    @abstractmethod
    def perform_request(self, *args, **kwargs):
        raise NotImplementedError
