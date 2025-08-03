# 🐍 There should be one-- and preferably only one --obvious way to do it.
# 🐼 任何问题应有一种，且最好只有一种，显而易见的解决方法
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/23 6:11
# @Update  : 2025/7/30 7:55
# @Detail  : 


"""
测试配置模块

测试lol_audio_unpack.u.config模块的功能
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lol_audio_unpack.utils.common import Singleton
from src.lol_audio_unpack.utils.config import Config, ConfigProxy, config


class TestConfig(unittest.TestCase):
    """测试Config类的功能"""

    def setUp(self):
        """测试前的准备工作"""
        # 创建临时目录作为测试环境
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_path = Path(self.test_dir.name)

        # 保存原始环境变量
        self.original_env = {}
        for param in Config.DEFAULT_PARAMS.keys():
            env_var = f"LOL_{param}"
            if env_var in os.environ:
                self.original_env[env_var] = os.environ[env_var]
                del os.environ[env_var]

        # 设置必要的配置项，避免警告
        os.environ["LOL_GAME_PATH"] = str(self.test_path / "game")
        os.environ["LOL_OUTPUT_PATH"] = str(self.test_path / "output")

        # 禁用日志文件写入，避免临时目录清理问题
        os.environ["LOL_DEBUG"] = "20"  # 仅控制台输出

        # 重置Config的单例实例，确保重新创建
        Config.reset_instance()

        # 重新创建一个干净的配置实例用于测试
        self.test_config = Config()

    def tearDown(self):
        """测试后的清理工作"""
        try:
            # 确保日志处理器被移除，释放文件锁
            import loguru

            loguru.logger.remove()

            # 清理临时目录
            self.test_dir.cleanup()
        except Exception as e:
            print(f"清理过程中出错: {e}")
            pass

        # 清理环境变量
        for param in Config.DEFAULT_PARAMS.keys():
            env_var = f"LOL_{param}"
            if env_var in os.environ:
                del os.environ[env_var]

        # 恢复原始环境变量
        for env_var, value in self.original_env.items():
            os.environ[env_var] = value

        # 重置单例
        Config.reset_instance()

    def test_singleton(self):
        """测试单例模式是否正常工作"""
        # 先重置确保干净状态
        Config.reset_instance()

        # 创建两个实例
        config1 = Config()
        config2 = Config()

        # 验证它们是同一个对象
        self.assertIs(config1, config2, "Config应该是单例模式")

        # 导入全局实例
        from src.lol_audio_unpack.utils.config import config as global_config

        # 打印两个实例的内存地址进行调试
        print(f"config1 id: {id(config1)}")
        print(f"global_config id: {id(global_config)}")

        # 这个断言可能会失败，因为全局config是在模块首次导入时创建的
        # 而测试中的Config()是新创建的，通过Reset后不同的实例
        # 只验证单例的基本功能，不验证与全局实例的关系
        # self.assertIs(global_config, config1, "全局config实例应该与Config()相同")

    def test_default_values(self):
        """测试默认值是否正确加载"""
        # 重置单例并清除环境变量
        Config.reset_instance()

        # 清除环境变量以确保使用默认值
        for param in Config.DEFAULT_PARAMS.keys():
            env_var = f"LOL_{param}"
            if env_var in os.environ:
                del os.environ[env_var]

        # 设置必要的配置项以避免警告，但不设置测试项
        os.environ["LOL_GAME_PATH"] = str(self.test_path / "game")
        os.environ["LOL_OUTPUT_PATH"] = str(self.test_path / "output")

        # 使用测试的配置实例
        default_config = Config(force_reload=True)

        # 检查默认值
        self.assertEqual(default_config.get("GAME_REGION"), "zh_CN")
        self.assertEqual(default_config.get("AUDIO_FORMATE"), "wem")
        self.assertEqual(default_config.get("DEBUG"), "5")
        self.assertEqual(default_config.get("INCLUDE_TYPE"), ["VO", "SFX", "MUSIC"])

    def test_set_get(self):
        """测试set和get方法"""
        test_config = self.test_config

        # 设置并获取值
        test_config.set("TEST_KEY", "test_value")
        self.assertEqual(test_config.get("TEST_KEY"), "test_value")

        # 测试默认值
        self.assertEqual(test_config.get("NON_EXISTENT_KEY", "default"), "default")

        # 测试覆盖值
        test_config.set("TEST_KEY", "new_value")
        self.assertEqual(test_config.get("TEST_KEY"), "new_value")

    def test_env_vars(self):
        """测试环境变量读取"""
        # 重置Config的单例实例
        Config.reset_instance()

        # 确保环境变量被正确设置
        os.environ["LOL_GAME_PATH"] = str(self.test_path / "game")
        os.environ["LOL_OUTPUT_PATH"] = str(self.test_path / "output")
        os.environ["LOL_GAME_REGION"] = "kr"
        os.environ["LOL_TEST_ENV"] = "env_value"

        # 打印当前环境变量进行调试
        print(f"当前环境变量 LOL_GAME_REGION = {os.environ.get('LOL_GAME_REGION')}")
        print(f"当前环境变量 LOL_TEST_ENV = {os.environ.get('LOL_TEST_ENV')}")

        # 强制创建新的配置实例 - 使用force_reload确保重新从环境变量加载
        new_config = Config(force_reload=True)

        # 打印配置值进行调试
        print(f"配置中 GAME_REGION = {new_config.get('GAME_REGION')}")
        print(f"配置来源 = {new_config.sources.get('GAME_REGION', 'unknown')}")
        print(f"配置中所有项: {list(new_config.settings.keys())}")

        # 验证环境变量是否被正确加载
        self.assertEqual(
            new_config.get("GAME_REGION"),
            "kr",
            f"环境变量未被正确加载，期望值:'kr', 实际值:{new_config.get('GAME_REGION')}",
        )

        # 检查自定义环境变量 - 这不在DEFAULT_PARAMS中定义，但应该被加载
        self.assertEqual(
            new_config.get("TEST_ENV"),
            "env_value",
            f"自定义环境变量未被加载，期望值:'env_value', 实际值:{new_config.get('TEST_ENV')}",
        )

    def test_path_generation(self):
        """测试派生路径生成"""
        test_config = self.test_config

        # 设置基本路径 (已在setUp中设置，但这里再次明确设置以确保测试的独立性)
        game_path = self.test_path / "game"
        output_path = self.test_path / "output"

        test_config.set("GAME_PATH", game_path)
        test_config.set("OUTPUT_PATH", output_path)

        # 手动触发路径生成
        test_config._generate_paths()

        # 验证派生路径是否正确生成
        self.assertEqual(test_config.get("AUDIO_PATH"), output_path / "audios")
        self.assertEqual(test_config.get("TEMP_PATH"), output_path / "temps")
        self.assertEqual(test_config.get("LOG_PATH"), output_path / "logs")
        self.assertEqual(test_config.get("GAME_CHAMPION_PATH"), game_path / "Game" / "DATA" / "FINAL" / "Champions")

    def test_type_conversion(self):
        """测试类型转换功能"""
        test_config = self.test_config

        # 测试路径转换
        test_config._set_value("GAME_PATH", str(self.test_path), "test")
        self.assertIsInstance(test_config.get("GAME_PATH"), Path)

        # 测试列表转换
        test_config._set_value("INCLUDE_TYPE", "type1, type2, type3", "test")
        self.assertIsInstance(test_config.get("INCLUDE_TYPE"), list)
        self.assertEqual(test_config.get("INCLUDE_TYPE"), ["type1", "type2", "type3"])

        # 测试整数转换
        test_config._set_value("DEBUG", "10", "test")
        self.assertEqual(test_config.get("DEBUG"), "10")  # DEBUG在参数定义中是字符串类型

    def test_as_dict(self):
        """测试as_dict方法"""
        test_config = self.test_config
        test_config.set("TEST_KEY1", "value1")
        test_config.set("TEST_KEY2", "value2")

        config_dict = test_config.as_dict()
        self.assertIsInstance(config_dict, dict)
        self.assertIn("TEST_KEY1", config_dict)
        self.assertIn("TEST_KEY2", config_dict)
        self.assertEqual(config_dict["TEST_KEY1"], "value1")
        self.assertEqual(config_dict["TEST_KEY2"], "value2")

    def test_config_proxy(self):
        """测试ConfigProxy类的功能"""
        # 重置单例状态
        Config.reset_instance()

        # 创建新的代理实例
        proxy = ConfigProxy()

        # 验证初始状态
        self.assertFalse(proxy.is_initialized())

        # 测试显式初始化
        os.environ["LOL_GAME_PATH"] = str(self.test_path / "game")
        os.environ["LOL_OUTPUT_PATH"] = str(self.test_path / "output")
        os.environ["LOL_TEST_PROXY"] = "proxy_value"

        proxy_config = proxy.initialize()

        # 验证初始化状态
        self.assertTrue(proxy.is_initialized())
        self.assertIsInstance(proxy_config, Config)

        # 验证配置值加载
        self.assertEqual(proxy.get("TEST_PROXY"), "proxy_value")

        # 测试属性访问
        self.assertEqual(proxy.get("GAME_PATH"), Path(str(self.test_path / "game")))

        # 测试方法转发
        config_dict = proxy.as_dict()
        self.assertIsInstance(config_dict, dict)
        self.assertIn("TEST_PROXY", config_dict)

    def test_config_proxy_default_params(self):
        """测试ConfigProxy的set_default_params方法"""
        # 重置单例状态
        Config.reset_instance()

        # 创建一个测试环境变量文件
        env_file = self.test_path / ".lol.env"
        with open(env_file, "w") as f:
            f.write("LOL_GAME_PATH=" + str(self.test_path / "custom_game") + "\n")
            f.write("LOL_OUTPUT_PATH=" + str(self.test_path / "custom_output") + "\n")
            f.write("LOL_CUSTOM_SETTING=default_param_value\n")

        # 创建代理实例并设置默认参数
        proxy = ConfigProxy()
        proxy.set_default_params(env_path=self.test_path)

        # 此时应该还未初始化
        self.assertFalse(proxy.is_initialized())

        # 首次访问将使用默认参数初始化
        custom_setting = proxy.get("CUSTOM_SETTING")

        # 验证已初始化
        self.assertTrue(proxy.is_initialized())

        # 验证使用了默认参数中的环境变量文件
        self.assertEqual(custom_setting, "default_param_value")
        self.assertEqual(proxy.get("GAME_PATH"), Path(str(self.test_path / "custom_game")))
        self.assertEqual(proxy.get("OUTPUT_PATH"), Path(str(self.test_path / "custom_output")))

    def test_dev_mode(self):
        """测试开发模式配置"""
        # 重置单例状态
        Config.reset_instance()

        # 创建常规环境变量文件
        env_file = self.test_path / ".lol.env"
        with open(env_file, "w") as f:
            f.write("LOL_GAME_PATH=" + str(self.test_path / "prod_game") + "\n")
            f.write("LOL_OUTPUT_PATH=" + str(self.test_path / "prod_output") + "\n")
            f.write("LOL_ENV_TYPE=production\n")

        # 创建开发环境变量文件
        dev_env_file = self.test_path / ".lol.env.dev"
        with open(dev_env_file, "w") as f:
            f.write("LOL_GAME_PATH=" + str(self.test_path / "dev_game") + "\n")
            f.write("LOL_OUTPUT_PATH=" + str(self.test_path / "dev_output") + "\n")
            f.write("LOL_ENV_TYPE=development\n")

        # 测试生产环境配置
        Config.reset_instance()
        prod_config = Config(env_path=self.test_path, dev_mode=False)
        self.assertEqual(prod_config.get("ENV_TYPE"), "production")
        self.assertEqual(prod_config.get("GAME_PATH"), Path(str(self.test_path / "prod_game")))
        self.assertFalse(prod_config.is_dev_mode())

        # 测试开发环境配置
        Config.reset_instance()
        dev_config = Config(env_path=self.test_path, dev_mode=True)
        self.assertEqual(dev_config.get("ENV_TYPE"), "development")
        self.assertEqual(dev_config.get("GAME_PATH"), Path(str(self.test_path / "dev_game")))
        self.assertTrue(dev_config.is_dev_mode())

    def test_default_project_root(self):
        """测试默认项目根目录配置"""
        # 重置单例状态
        Config.reset_instance()

        # 获取当前工作目录
        from src.lol_audio_unpack.utils.config import WORK_DIR

        try:
            # 在没有指定env_path时测试配置行为
            no_path_config = Config()

            # 验证它使用了预期的默认路径
            self.assertEqual(no_path_config.get("GAME_PATH"), Path(str(self.test_path / "game")))
            self.assertEqual(no_path_config.get("OUTPUT_PATH"), Path(str(self.test_path / "output")))

            # 检查配置实例是否使用了当前工作目录
            self.assertIn("Using working directory as default", str(no_path_config))
        finally:
            # 确保我们不会影响其他测试
            Config.reset_instance()

    def test_singleton_pattern(self):
        """测试单例模式是否生效"""
        from src.lol_audio_unpack.utils.config import config as global_config

        self.assertIs(config, global_config, "Config 实例应该是单例")

    def test_work_dir_constant(self):
        """测试 WORK_DIR 常量是否正确"""
        from src.lol_audio_unpack.utils.config import WORK_DIR

        self.assertIsInstance(WORK_DIR, Path)
        self.assertTrue(str(WORK_DIR).endswith("lol_audio_unpack"))


if __name__ == "__main__":
    unittest.main()
