import pytest
from bci_tester.data import DOTNET_ASPNET_5_0_BASE_CONTAINER
from bci_tester.data import DOTNET_SDK_5_0_BASE_CONTAINER
from bci_tester.data import EXTRA_BUILD_ARGS
from bci_tester.data import GO_1_16_CONTAINER
from bci_tester.data import MultiStageBuild
from bci_tester.data import OPENJDK_BASE_CONTAINER
from bci_tester.data import OPENJDK_DEVEL_BASE_CONTAINER
from bci_tester.helpers import GitRepositoryBuild
from bci_tester.helpers import LOCALHOST


MAVEN_VERSION = "3.8.2"


@pytest.mark.parametrize(
    "host_git_clone,multi_stage_build,retval,cmd_stdout",
    [
        (
            GitRepositoryBuild(
                repository_url="https://github.com/toolbox4minecraft/amidst",
                repository_tag="v4.7",
            ),
            MultiStageBuild(
                OPENJDK_DEVEL_BASE_CONTAINER,
                OPENJDK_BASE_CONTAINER,
                """
        FROM $builder as builder
        WORKDIR /amidst
        COPY ./amidst .
        RUN mvn package -DskipTests=True
        FROM $runner
        WORKDIR /amidst/
        COPY --from=builder /amidst/target .
        CMD ["java", "-jar", "amidst-v4-7.jar"]
        """,
            ),
            0,
            "[info] Amidst v4.7",
        ),
        (
            GitRepositoryBuild(
                repository_url="https://github.com/apache/maven",
                repository_tag=f"maven-{MAVEN_VERSION}",
            ),
            MultiStageBuild(
                OPENJDK_DEVEL_BASE_CONTAINER,
                OPENJDK_DEVEL_BASE_CONTAINER,
                f"""
        FROM $builder as builder
        WORKDIR /maven
        COPY ./maven .
        RUN mvn package && zypper -n in unzip && \
            unzip /maven/apache-maven/target/apache-maven-{MAVEN_VERSION}-bin.zip
        FROM $runner
        WORKDIR /maven/
        COPY --from=builder /maven/apache-maven-{MAVEN_VERSION}/ .
        CMD ["/maven/bin/mvn"]
        """,
            ),
            1,
            "[ERROR] No goals have been specified for this build.",
        ),
        (
            GitRepositoryBuild(
                repository_tag="v3.3.1",
                repository_url="https://gitlab.com/pdftk-java/pdftk.git",
            ),
            MultiStageBuild(
                OPENJDK_DEVEL_BASE_CONTAINER,
                OPENJDK_BASE_CONTAINER,
                """FROM $builder as builder
        WORKDIR /pdftk
        COPY ./pdftk .
        RUN zypper --non-interactive addrepo https://download.opensuse.org/repositories/Java:/packages/openSUSE_Leap_15.3/Java:packages.repo && \
            zypper --non-interactive --gpg-auto-import-keys ref && \
            zypper --non-interactive in apache-ant apache-ivy && \
            ant test-resolve && ant compile && ant jar
        FROM $runner
        WORKDIR /pdftk/
        COPY --from=builder /pdftk/build/jar/pdftk.jar .
        CMD ["java", "-jar", "pdftk.jar"]
        """,
            ),
            0,
            """SYNOPSIS
       pdftk <input PDF files | - | PROMPT>
        """,
        ),
        (
            GitRepositoryBuild(
                repository_tag="0.11.1",
                repository_url="https://github.com/alexellis/k3sup",
            ),
            MultiStageBuild(
                GO_1_16_CONTAINER,
                "scratch",
                """FROM $builder as builder
WORKDIR /k3sup
COPY ./k3sup .
RUN echo > ./hack/hashgen.sh && make all

FROM $runner
WORKDIR /k3sup
COPY --from=builder /k3sup/bin/k3sup .
CMD ["/k3sup/k3sup"]
""",
            ),
            0,
            'Use "k3sup [command] --help" for more information about a command.',
        ),
        pytest.param(
            GitRepositoryBuild(
                repository_url="https://github.com/phillipsj/adventureworks-k8s-sample.git"
            ),
            MultiStageBuild(
                builder=DOTNET_SDK_5_0_BASE_CONTAINER,
                runner=DOTNET_ASPNET_5_0_BASE_CONTAINER,
                # modified version of upstream's Dockerfile:
                # - the entrypoint.sh is custom, so that the application
                #   terminates
                # - the docker build is not run from the repos top level dir,
                #   but one directory "above"
                dockerfile_template=r"""FROM $builder AS build
WORKDIR /src

COPY ./adventureworks-k8s-sample/AdventureWorks.sln AdventureWorks.sln
COPY ./adventureworks-k8s-sample/AdventureWorks.App/*.csproj ./AdventureWorks.App/
COPY ./adventureworks-k8s-sample/BlazorLeaflet/*.csproj ./BlazorLeaflet/
RUN dotnet restore AdventureWorks.sln

COPY ./adventureworks-k8s-sample/AdventureWorks.App/. ./AdventureWorks.App/
COPY ./adventureworks-k8s-sample/BlazorLeaflet/. ./BlazorLeaflet/

RUN dotnet publish -c release -o /app --no-restore

FROM $runner
WORKDIR /app
COPY --from=build /app ./
RUN zypper -n in curl
RUN echo $$'#!/bin/bash -e \n\
dotnet AdventureWorks.App.dll & \n\
c=0 \n\
until curl localhost:5000 >/dev/null ; do \n\
  ((c++)) && ((c==20)) && ( \n\
    curl localhost:5000|grep Adventure \n\
    exit 1 \n\
  ) \n\
  sleep 1 \n\
done \n\
pkill dotnet \n\
' > entrypoint.sh && chmod +x entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
""",
            ),
            0,
            """Microsoft.Hosting.Lifetime[0]\n      Now listening on: http://localhost:5000
\x1b[40m\x1b[32minfo\x1b[39m\x1b[22m\x1b[49m: Microsoft.Hosting.Lifetime[0]
      Application started. Press Ctrl+C to shut down.
\x1b[40m\x1b[32minfo\x1b[39m\x1b[22m\x1b[49m: Microsoft.Hosting.Lifetime[0]
      Hosting environment: Production
\x1b[40m\x1b[32minfo\x1b[39m\x1b[22m\x1b[49m: Microsoft.Hosting.Lifetime[0]
      Content root path: /app
""",
            marks=pytest.mark.skipif(
                LOCALHOST.system_info.arch != "x86_64",
                reason="The dotnet containers are only available for x86_64",
            ),
        ),
    ],
    indirect=["host_git_clone"],
)
def test_dockerfile_build(
    host,
    container_runtime,
    host_git_clone,
    multi_stage_build: MultiStageBuild,
    retval: int,
    cmd_stdout: str,
):
    tmp_path, _ = host_git_clone

    multi_stage_build.prepare_build(tmp_path)

    cmd = host.run_expect(
        [0],
        f"{' '.join(container_runtime.build_command + EXTRA_BUILD_ARGS)} {tmp_path}",
    )
    img_id = container_runtime.get_image_id_from_stdout(cmd.stdout)

    assert (
        cmd_stdout
        in host.run_expect(
            [retval], f"{container_runtime.runner_binary} run --rm {img_id}"
        ).stdout
    )
