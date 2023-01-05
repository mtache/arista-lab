containerlab_image := ghcr.io/srl-labs/clab

mkfile_path := $(abspath $(lastword $(MAKEFILE_LIST)))
mkfile_dir := $(dir $(mkfile_path))
containerlab = docker run --rm -it --privileged \
    --network host \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /run/netns:/run/netns \
    --platform linux/amd64 \
    --pid="host" \
    -w "${mkfile_dir}" \
    -v "${mkfile_dir}":"${mkfile_dir}" \
    ${containerlab_image} containerlab $(1)

graph = docker run --rm -it \
    -p 50080:50080 \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /run/netns:/run/netns \
    --platform linux/amd64 \
    --pid="host" \
    -w "${mkfile_dir}" \
    -v "${mkfile_dir}":"${mkfile_dir}" \
    ${containerlab_image} containerlab graph

pull:
	docker pull ${containerlab_image}

all: pull
	lab init
	@$(call containerlab,deploy)
	lab onboard --token cv-onboarding-token

deploy: pull
	@$(call containerlab,deploy)

graph: pull
	@$(call graph)

clean:
	@$(call containerlab,destroy -c)
	rm -rf nornir.log .*.clab.yml*