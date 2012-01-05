import logging, logging.config, os

class SSSLogger(object):
    def __init__(self):
        self.logging_config = "./sss_logging.conf"  # default
        self.basic_config = """[loggers]
keys=root

[handlers]
keys=consoleHandler

[formatters]
keys=basicFormatting

[logger_root]
level=INFO
handlers=consoleHandler

[handler_consoleHandler]
class=StreamHandler
level=DEBUG
formatter=basicFormatting
args=(sys.stdout,)

[formatter_basicFormatting]
format=%(asctime)s - %(name)s - %(levelname)s - %(message)s
"""

        if not os.path.isfile(self.logging_config):
            self.create_logging_config(self.logging_config)

        logging.config.fileConfig(self.logging_config)

    def create_logging_config(self, pathtologgingconf):
        fn = open(pathtologgingconf, "w")
        fn.write(self.basic_config)
        fn.close()
        
    def getLogger(self):
        return logging.getLogger(__name__)
        
